import asyncio

# --- PATCH PER PYTHON 3.14 & STREAMLIT ---
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

_old_get_event_loop = asyncio.get_event_loop


def _safe_get_event_loop():
    try:
        return _old_get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


asyncio.get_event_loop = _safe_get_event_loop

from datetime import datetime
import json
import os
import urllib.parse
import pandas as pd
import streamlit as st

# Configurazione della pagina
st.set_page_config(
    page_title="Gestione Incassi - USO Nuvolento",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Importi di riferimento (su quota base 260 €: acconto 100 € + saldo 160 €)
IMPORTO_ACCONTO_BASE = 100
IMPORTO_SALDO_BASE = 160
PIN_ADMIN_DEFAULT = "Uso2011"
PIN_MODIFICA_DEFAULT = "Uso2011"
METODI_PAGAMENTO = ["Contanti", "Bonifico"]

# --- GESTIONE PERSISTENZA DATI (FILE JSON) ---
FILE_DATI = "dati_pagamenti.json"


def ordina_per_cognome(lista_giocatori):
    return sorted(
        lista_giocatori,
        key=lambda x: x.split(" ", 1)[1] if " " in x else x,
    )


def get_importi_spunte(quota_unitaria):
    if quota_unitaria == 260:
        return IMPORTO_ACCONTO_BASE, IMPORTO_SALDO_BASE
    acconto = min(IMPORTO_ACCONTO_BASE, max(0, quota_unitaria))
    saldo = max(0, quota_unitaria - acconto)
    return acconto, saldo


def normalizza_record_pagamento(stato_record):
    """Restituisce (has_acconto, has_pagato, metodo_acconto, metodo_pagato)."""
    if isinstance(stato_record, dict):
        has_acconto = bool(stato_record.get("acconto", False))
        has_pagato = bool(stato_record.get("pagato", False))
        m_acc = stato_record.get("metodo_acconto", "Contanti")
        m_pag = stato_record.get("metodo_pagato", "Contanti")
        if m_acc not in METODI_PAGAMENTO:
            m_acc = "Contanti"
        if m_pag not in METODI_PAGAMENTO:
            m_pag = "Contanti"
        return has_acconto, has_pagato, m_acc, m_pag
    return False, bool(stato_record), "Contanti", "Contanti"


def calcola_quota_giocatore(stato_record, quota_unitaria, num_persone):
    """Restituisce (importo_incassato, stato_testo, has_acconto, has_pagato, m_acc, m_pag)."""
    has_acconto, has_pagato, m_acc, m_pag = normalizza_record_pagamento(
        stato_record
    )

    val_acconto, val_saldo = get_importi_spunte(quota_unitaria)
    quota_unit_incassata = (val_acconto if has_acconto else 0) + (
        val_saldo if has_pagato else 0
    )
    importo_incassato = quota_unit_incassata * num_persone
    totale_dovuto = quota_unitaria * num_persone

    if totale_dovuto > 0 and importo_incassato >= totale_dovuto:
        stato = "PAGATO"
    elif importo_incassato > 0:
        stato = "ACCONTO"
    else:
        stato = "IN ATTESA"

    return importo_incassato, stato, has_acconto, has_pagato, m_acc, m_pag


def record_pagamento_vuoto():
    return {
        "acconto": False,
        "pagato": False,
        "metodo_acconto": "Contanti",
        "metodo_pagato": "Contanti",
    }


def struttura_default():
    giocatori_iniziali = [
        "Rossi Mario",
        "Bianchi Luca",
        "Verdi Alessandro",
        "Ferrari Marco",
        "Russo Giovanni",
        "Esposito Davide",
        "Romano Andrea",
        "Colombo Matteo",
        "Ricci Simone",
        "Marino Filippo",
    ]

    giocatori_ordinati = ordina_per_cognome(giocatori_iniziali)
    partecipanti_iniziali = {g: 1 for g in giocatori_ordinati}
    pagamenti_iniziali = {
        g: record_pagamento_vuoto() for g in giocatori_ordinati
    }

    return {
        "admin_pin": PIN_ADMIN_DEFAULT,
        "utenti": {
            "Admin": {"ruolo": "modifica", "pin": PIN_MODIFICA_DEFAULT},
            "Dirigente": {"ruolo": "modifica", "pin": PIN_MODIFICA_DEFAULT},
            "Sola Lettura": {"ruolo": "lettura", "pin": ""},
        },
        "progetti": {
            "Torneo Lignano Sabbiadoro (Under 16 - 2011)": {
                "quota": 260,
                "giocatori": giocatori_ordinati,
                "pagamenti": pagamenti_iniziali,
                "partecipanti": partecipanti_iniziali,
            }
        },
    }


def estrai_utente_sicuro(utenti_dict, nome_utente):
    """Restituisce sempre un dizionario {'ruolo': ..., 'pin': ...} valido."""
    raw = utenti_dict.get(nome_utente) if isinstance(utenti_dict, dict) else None
    if isinstance(raw, dict):
        ruolo = raw.get("ruolo")
        if ruolo not in ("modifica", "lettura"):
            ruolo = "lettura"
        if ruolo == "modifica":
            pin_raw = raw.get("pin")
            pin = (
                str(pin_raw).strip()
                if pin_raw is not None and str(pin_raw).strip() != ""
                else PIN_MODIFICA_DEFAULT
            )
        else:
            pin = ""
        return {"ruolo": ruolo, "pin": pin}
    elif isinstance(raw, str) and raw in ("modifica", "lettura"):
        return {
            "ruolo": raw,
            "pin": PIN_MODIFICA_DEFAULT if raw == "modifica" else "",
        }
    return {"ruolo": "lettura", "pin": ""}


def normalizza_utenti(utenti_grezzi):
    default_utenti = struttura_default()["utenti"]
    if not isinstance(utenti_grezzi, dict) or not utenti_grezzi:
        return dict(default_utenti)

    normalizzati = {}
    for nome in utenti_grezzi.keys():
        if nome is None or str(nome).strip() == "":
            continue
        chiave = str(nome).strip()
        normalizzati[chiave] = estrai_utente_sicuro(utenti_grezzi, nome)

    return normalizzati or dict(default_utenti)


def normalizza_stato_completo(grezzo):
    default = struttura_default()
    if not isinstance(grezzo, dict) or not grezzo:
        return default

    if "progetti" not in grezzo:
        progetti = grezzo
        admin_pin = PIN_ADMIN_DEFAULT
        utenti = dict(default["utenti"])
    else:
        progetti = grezzo.get("progetti") or default["progetti"]
        admin_pin_raw = grezzo.get("admin_pin")
        admin_pin = (
            str(admin_pin_raw).strip()
            if admin_pin_raw is not None and str(admin_pin_raw).strip() != ""
            else PIN_ADMIN_DEFAULT
        )
        utenti = normalizza_utenti(grezzo.get("utenti"))

    for proj in progetti.values():
        if isinstance(proj, dict) and "giocatori" in proj:
            proj["giocatori"] = ordina_per_cognome(proj["giocatori"])
            if "partecipanti" not in proj or not isinstance(proj["partecipanti"], dict):
                proj["partecipanti"] = {g: 1 for g in proj["giocatori"]}
            if "pagamenti" not in proj or not isinstance(proj["pagamenti"], dict):
                proj["pagamenti"] = {}
            for g in proj["giocatori"]:
                has_a, has_p, m_a, m_p = normalizza_record_pagamento(
                    proj["pagamenti"].get(g, record_pagamento_vuoto())
                )
                proj["pagamenti"][g] = {
                    "acconto": has_a,
                    "pagato": has_p,
                    "metodo_acconto": m_a,
                    "metodo_pagato": m_p,
                }
                if g not in proj["partecipanti"]:
                    proj["partecipanti"][g] = 1

    return {
        "admin_pin": admin_pin,
        "utenti": utenti,
        "progetti": progetti,
    }


def carica_dati():
    if os.path.exists(FILE_DATI):
        try:
            with open(FILE_DATI, "r", encoding="utf-8") as f:
                grezzo = json.load(f)
                return normalizza_stato_completo(grezzo)
        except Exception:
            pass
    return struttura_default()


def salva_dati(stato_app):
    with open(FILE_DATI, "w", encoding="utf-8") as f:
        json.dump(stato_app, f, ensure_ascii=False, indent=4)
    st.session_state.ultimo_salvataggio = datetime.now().strftime("%H:%M:%S")


def serializza_json(stato_app):
    return json.dumps(stato_app, ensure_ascii=False, indent=4).encode("utf-8")


# --- FUNZIONE PER ESPORTARE IN CSV ---
def genera_csv(progetto_nome, dati_progetto):
    giocatori = dati_progetto["giocatori"]
    pagamenti = dati_progetto["pagamenti"]
    partecipanti = dati_progetto.get("partecipanti", {})
    quota = dati_progetto["quota"]

    data_list = []
    for g in giocatori:
        num_persone = partecipanti.get(g, 1)
        totale_dovuto = quota * num_persone
        (
            totale_pagato,
            stato,
            has_acconto,
            has_pagato,
            m_acc,
            m_pag,
        ) = calcola_quota_giocatore(
            pagamenti.get(g, record_pagamento_vuoto()),
            quota,
            num_persone,
        )

        data_list.append(
            {
                "Giocatore": g,
                "Partecipanti al seguito": num_persone,
                "Acconto (100€)": "SI" if has_acconto else "NO",
                "Metodo Acconto": m_acc if has_acconto else "",
                "Pagato (160€)": "SI" if has_pagato else "NO",
                "Metodo Pagato": m_pag if has_pagato else "",
                "Stato Pagamento": stato,
                "Quota Unitaria (€)": quota,
                "Totale Dovuto (€)": totale_dovuto,
                "Totale Incassato (€)": totale_pagato,
                "Residuo (€)": max(0, totale_dovuto - totale_pagato),
            }
        )

    df = (
        pd.DataFrame(data_list)
        if data_list
        else pd.DataFrame(
            columns=[
                "Giocatore",
                "Partecipanti al seguito",
                "Acconto (100€)",
                "Metodo Acconto",
                "Pagato (160€)",
                "Metodo Pagato",
                "Stato Pagamento",
                "Quota Unitaria (€)",
                "Totale Dovuto (€)",
                "Totale Incassato (€)",
                "Residuo (€)",
            ]
        )
    )

    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


# --- CSS PERSONALIZZATO ---
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        .stApp {
            background-color: #f8fafc;
            color: #0f172a;
        }

        h1, h2, h3, h4, h5, h6, p, span, label {
            color: #0f172a !important;
        }

        [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            align-items: center !important;
            gap: 2px !important;
        }

        [data-testid="stColumn"] {
            min-width: 0 !important;
            flex: 1 1 auto !important;
            padding-left: 1px !important;
            padding-right: 1px !important;
        }

        .stButton button {
            border-radius: 6px;
            font-weight: 600;
            min-height: 30px;
            max-height: 36px;
            padding: 0px 4px !important;
            font-size: 0.75rem;
        }

        button[kind="primary"] {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
            border: none !important;
            color: white !important;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
        }

        div[data-testid="stMetric"] {
            background-color: #ffffff;
            padding: 10px 12px;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            height: auto !important;
            min-height: 90px;
            margin-bottom: 8px;
        }
        div[data-testid="stMetric"] label {
            color: #64748b !important;
            font-weight: 500;
            white-space: normal !important;
            word-break: break-word !important;
            font-size: 0.8rem !important;
        }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: #0f172a !important;
            font-weight: 700;
            white-space: normal !important;
            word-break: break-word !important;
            font-size: 0.95rem !important;
        }

        details {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 5px;
            margin-bottom: 15px;
        }

        .stSelectbox div[data-baseweb="select"], .stTextInput input {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border-radius: 6px !important;
            border-color: #cbd5e1 !important;
        }

        /* Riduzione font e ingombro dei menu a discesa (Contanti / Bonifico) */
        .row-riga-giocatore [data-testid="stSelectbox"] > div > div {
            min-height: 28px !important;
            height: 28px !important;
            padding-top: 0px !important;
            padding-bottom: 0px !important;
            padding-left: 4px !important;
            padding-right: 4px !important;
        }
        .row-riga-giocatore [data-testid="stSelectbox"] span,
        .row-riga-giocatore [data-testid="stSelectbox"] div {
            font-size: 0.62rem !important;
            line-height: 1.1 !important;
        }
        .row-riga-giocatore [data-testid="stCheckbox"] label span {
            font-size: 0.65rem !important;
        }
        .row-riga-giocatore [data-testid="stNumberInput"] input {
            font-size: 0.68rem !important;
            padding: 2px 4px !important;
            min-height: 28px !important;
            height: 28px !important;
        }

        @media (max-width: 640px) {
            .block-container {
                padding-left: 3px !important;
                padding-right: 3px !important;
                padding-top: 15px !important;
            }
            h1 {
                font-size: 1.4rem !important;
            }
            .row-riga-giocatore [data-testid="stSelectbox"] span,
            .row-riga-giocatore [data-testid="stSelectbox"] div {
                font-size: 0.55rem !important;
            }
            .row-riga-giocatore [data-testid="stCheckbox"] label span {
                font-size: 0.58rem !important;
            }
        }
    </style>
""",
    unsafe_allow_html=True,
)

# Inizializzazione dello stato caricando dal file JSON
if "stato_app" not in st.session_state:
    st.session_state.stato_app = carica_dati()
else:
    st.session_state.stato_app = normalizza_stato_completo(st.session_state.stato_app)

stato_app = st.session_state.stato_app
utenti_dict = stato_app["utenti"]

if "autenticato" not in st.session_state:
    st.session_state.autenticato = False

if "utente_attivo" not in st.session_state or st.session_state.utente_attivo not in utenti_dict:
    st.session_state.utente_attivo = None
    st.session_state.autenticato = False

if "admin_sbloccato" not in st.session_state:
    st.session_state.admin_sbloccato = False

if "ultimo_salvataggio" not in st.session_state:
    st.session_state.ultimo_salvataggio = (
        datetime.now().strftime("%H:%M:%S")
        if os.path.exists(FILE_DATI)
        else "Non ancora salvato"
    )

# Intestazione App
st.markdown(
    "<h1 style='text-align: center; margin-bottom: 0;'>⚽ Gestione Incassi</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align: center; color: #64748b; margin-top: 2px; font-size: 0.9em;'>USO Nuvolento - Monitoraggio Quote</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

# --- SCHERMATA DI ACCESSO (PRIMA DI ENTRARE NELL'APP) ---
if not st.session_state.autenticato or not st.session_state.utente_attivo:
    st.markdown("### 🔐 Accesso all'Applicazione")
    st.markdown(
        "<p style='color: #64748b; font-size: 0.85em;'>Seleziona l'utente. Il PIN è richiesto per gli utenti con accesso di <b>modifica</b>.</p>",
        unsafe_allow_html=True,
    )

    lista_utenti_login = list(utenti_dict.keys())
    utente_login = st.selectbox(
        "Seleziona utente",
        options=lista_utenti_login,
        key="login_utente_select",
    )
    info_login = estrai_utente_sicuro(utenti_dict, utente_login)
    ruolo_login = info_login["ruolo"]
    richiede_pin = ruolo_login == "modifica"

    pin_login = ""
    if richiede_pin:
        pin_login = st.text_input(
            "PIN",
            type="password",
            key="login_pin_input",
            placeholder="Inserisci PIN",
        )
    else:
        st.info(
            "Utente in **sola lettura**: nessun PIN richiesto per consultare i dati."
        )

    label_btn_login = (
        "🔓 Accedi con PIN"
        if richiede_pin
        else "👁️ Entra in Sola Lettura"
    )
    if st.button(label_btn_login, type="primary", use_container_width=True):
        if not richiede_pin:
            st.session_state.utente_attivo = utente_login
            st.session_state.autenticato = True
            st.session_state.admin_sbloccato = False
            st.rerun()
        else:
            pin_corretto = info_login["pin"]
            if pin_login == pin_corretto:
                st.session_state.utente_attivo = utente_login
                st.session_state.autenticato = True
                st.session_state.admin_sbloccato = False
                st.rerun()
            else:
                st.error("PIN errato per l'accesso in modifica.")

    st.stop()

# --- APP AUTENTICATA ---
utente_corrente = st.session_state.utente_attivo
info_corrente = estrai_utente_sicuro(utenti_dict, utente_corrente)
ruolo_corrente = info_corrente["ruolo"]
puo_modificare = ruolo_corrente == "modifica"

col_u_info, col_u_badge, col_u_logout = st.columns([1.8, 1.2, 1.0])
with col_u_info:
    st.markdown(
        f"<div style='padding-top: 6px; font-weight: 600; font-size: 0.88rem;'>👤 {utente_corrente}</div>",
        unsafe_allow_html=True,
    )
with col_u_badge:
    if puo_modificare:
        st.markdown(
            "<div style='padding-top: 6px; text-align: center;'><span style='background-color: #d1fae5; color: #065f46; padding: 3px 8px; border-radius: 6px; font-size: 0.7em; font-weight: 700;'>✏️ MODIFICA</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='padding-top: 6px; text-align: center;'><span style='background-color: #e2e8f0; color: #334155; padding: 3px 8px; border-radius: 6px; font-size: 0.7em; font-weight: 700;'>👁️ LETTURA</span></div>",
            unsafe_allow_html=True,
        )
with col_u_logout:
    if st.button("🚪 Esci", key="btn_logout", use_container_width=True):
        st.session_state.autenticato = False
        st.session_state.utente_attivo = None
        st.session_state.admin_sbloccato = False
        st.rerun()

if not puo_modificare:
    st.info(
        f"Stai visualizzando l'app come **{utente_corrente}** in modalità **sola lettura**. Le modifiche sono disabilitate."
    )
else:
    with st.expander("🔑 Cambia il tuo PIN di accesso"):
        pin_attuale_inp = st.text_input(
            "PIN attuale", type="password", key="mio_pin_attuale"
        )
        pin_nuovo_inp = st.text_input(
            "Nuovo PIN", type="password", key="mio_pin_nuovo"
        )
        pin_conferma_inp = st.text_input(
            "Conferma nuovo PIN", type="password", key="mio_pin_conferma"
        )
        if st.button("Salva nuovo PIN", use_container_width=True):
            pin_registrato = info_corrente["pin"]
            if pin_attuale_inp != pin_registrato:
                st.error("Il PIN attuale non è corretto.")
            elif not pin_nuovo_inp.strip():
                st.warning("Inserisci un nuovo PIN non vuoto.")
            elif pin_nuovo_inp != pin_conferma_inp:
                st.warning("La conferma del nuovo PIN non coincide.")
            else:
                utenti_dict[utente_corrente] = {
                    "ruolo": "modifica",
                    "pin": pin_nuovo_inp.strip(),
                }
                salva_dati(stato_app)
                st.success("PIN aggiornato correttamente!")
                st.rerun()

# --- PANNELLO AMMINISTRATORE (ACCESSO TRAMITE PIN) ---
with st.expander("🔐 Pannello Amministratore (PIN)"):
    if not st.session_state.admin_sbloccato:
        pin_inserito = st.text_input(
            "Inserisci PIN Amministratore",
            type="password",
            key="input_pin_admin",
            placeholder="Inserisci PIN",
        )
        if st.button("Sblocca Pannello Admin", use_container_width=True):
            if pin_inserito == stato_app.get("admin_pin", PIN_ADMIN_DEFAULT):
                st.session_state.admin_sbloccato = True
                st.success("Pannello amministratore sbloccato.")
                st.rerun()
            else:
                st.error("PIN errato.")
    else:
        st.success("Accesso amministratore attivo.")
        if st.button("🔒 Blocca Pannello Admin", use_container_width=True):
            st.session_state.admin_sbloccato = False
            st.rerun()

        st.markdown("#### 👥 Utenti, PIN e Permessi")
        for u_nome in list(utenti_dict.keys()):
            u_info = estrai_utente_sicuro(utenti_dict, u_nome)
            u_ruolo_att = u_info["ruolo"]
            u_pin_att = u_info["pin"]

            c_un, c_ur, c_up, c_ud = st.columns([1.8, 1.4, 1.2, 0.6])
            with c_un:
                st.markdown(
                    f"<div style='padding-top: 6px; font-weight: 600; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{u_nome}</div>",
                    unsafe_allow_html=True,
                )
            with c_ur:
                nuovo_ruolo = st.selectbox(
                    f"Ruolo {u_nome}",
                    options=["modifica", "lettura"],
                    index=0 if u_ruolo_att == "modifica" else 1,
                    key=f"ruolo_{u_nome}",
                    label_visibility="collapsed",
                )
                if nuovo_ruolo != u_ruolo_att:
                    utenti_dict[u_nome] = {
                        "ruolo": nuovo_ruolo,
                        "pin": PIN_MODIFICA_DEFAULT if nuovo_ruolo == "modifica" else "",
                    }
                    salva_dati(stato_app)
                    st.rerun()
            with c_up:
                if u_ruolo_att == "modifica":
                    nuovo_pin_u = st.text_input(
                        f"PIN {u_nome}",
                        value=u_pin_att or PIN_MODIFICA_DEFAULT,
                        key=f"pin_u_{u_nome}",
                        label_visibility="collapsed",
                    )
                    if nuovo_pin_u.strip() and nuovo_pin_u.strip() != u_pin_att:
                        utenti_dict[u_nome] = {
                            "ruolo": "modifica",
                            "pin": nuovo_pin_u.strip(),
                        }
                        salva_dati(stato_app)
                        st.rerun()
                else:
                    st.markdown(
                        "<div style='padding-top: 6px; text-align: center; color: #64748b; font-size: 0.72rem;'>No PIN</div>",
                        unsafe_allow_html=True,
                    )
            with c_ud:
                if len(utenti_dict) > 1:
                    if st.button("🗑️", key=f"del_user_{u_nome}", use_container_width=True):
                        del utenti_dict[u_nome]
                        if st.session_state.utente_attivo == u_nome:
                            st.session_state.autenticato = False
                            st.session_state.utente_attivo = None
                        salva_dati(stato_app)
                        st.rerun()
                else:
                    st.markdown(
                        "<div style='padding-top: 6px; text-align: center; color: #94a3b8; font-size: 0.75rem;'>—</div>",
                        unsafe_allow_html=True,
                    )

        st.markdown("#### ➕ Aggiungi Nuovo Utente")
        nuovo_utente_nome = st.text_input(
            "Nome utente", key="nuovo_utente_nome", placeholder="Es. Mister Fabio"
        )
        nuovo_utente_ruolo = st.selectbox(
            "Livello accesso",
            options=["modifica", "lettura"],
            format_func=lambda r: "Modifica" if r == "modifica" else "Sola lettura",
            key="nuovo_utente_ruolo",
        )
        nuovo_utente_pin = ""
        if nuovo_utente_ruolo == "modifica":
            nuovo_utente_pin = st.text_input(
                "PIN iniziale",
                key="nuovo_utente_pin",
                placeholder="Inserisci PIN",
            )
        if st.button("Aggiungi Utente", use_container_width=True):
            nome_pulito = nuovo_utente_nome.strip()
            if nuovo_utente_ruolo == "modifica":
                pin_pulito = nuovo_utente_pin.strip() or PIN_MODIFICA_DEFAULT
            else:
                pin_pulito = ""
            if nome_pulito and nome_pulito not in utenti_dict:
                utenti_dict[nome_pulito] = {
                    "ruolo": nuovo_utente_ruolo,
                    "pin": pin_pulito,
                }
                salva_dati(stato_app)
                st.success(f"Utente '{nome_pulito}' aggiunto ({nuovo_utente_ruolo}).")
                st.rerun()
            elif nome_pulito in utenti_dict:
                st.warning("Esiste già un utente con questo nome.")
            else:
                st.warning("Inserisci un nome utente valido.")

        st.markdown("#### 🔑 Cambia PIN Pannello Amministratore")
        nuovo_pin_admin = st.text_input(
            "Nuovo PIN Admin", type="password", key="nuovo_pin_admin"
        )
        if st.button("Aggiorna PIN Admin", use_container_width=True):
            if nuovo_pin_admin.strip():
                stato_app["admin_pin"] = nuovo_pin_admin.strip()
                salva_dati(stato_app)
                st.success("PIN amministratore aggiornato.")
            else:
                st.warning("Inserisci un PIN non vuoto.")

st.markdown("---")

# --- SEZIONE 1: Gestione Progetti e Selezione ---
st.markdown("### 📁 Progetto Attivo")

progetti = stato_app["progetti"]
col_sel, col_add = st.columns([2, 1])

with col_sel:
    lista_progetti = list(progetti.keys())
    progetto_selezionato = st.selectbox(
        "Progetto attivo", lista_progetti, label_visibility="collapsed"
    )

with col_add:
    with st.popover("➕ Nuovo", use_container_width=True, disabled=not puo_modificare):
        nuovo_nome = st.text_input("Nome Progetto")
        nuova_quota = st.number_input(
            "Quota (€)", min_value=0, value=260, step=10
        )
        if st.button("Crea", use_container_width=True, disabled=not puo_modificare):
            if nuovo_nome and nuovo_nome not in progetti:
                progetti[nuovo_nome] = {
                    "quota": nuova_quota,
                    "giocatori": [],
                    "pagamenti": {},
                    "partecipanti": {},
                }
                salva_dati(stato_app)
                st.success(f"'{nuovo_nome}' creato!")
                st.rerun()

dati_attivi = progetti[progetto_selezionato]
quota_unitaria = dati_attivi["quota"]
giocatori = dati_attivi["giocatori"]
pagamenti_dict = dati_attivi["pagamenti"]
partecipanti_dict = dati_attivi["partecipanti"]
tot_giocatori = len(giocatori)

val_acconto_u, val_saldo_u = get_importi_spunte(quota_unitaria)

# Calcoli finanziari e conteggi
valore_totale_atteso = 0
valore_incassato = 0
giocatori_saldati = 0
giocatori_acconto = 0
totale_partecipanti_teorico = 0
partecipanti_saldati = 0

for g in giocatori:
    num_p = partecipanti_dict.get(g, 1)
    totale_partecipanti_teorico += num_p
    dovuto_g = quota_unitaria * num_p
    valore_totale_atteso += dovuto_g
    inc_g, stato_g, _, _, _, _ = calcola_quota_giocatore(
        pagamenti_dict.get(g, record_pagamento_vuoto()),
        quota_unitaria,
        num_p,
    )
    valore_incassato += inc_g
    if stato_g == "PAGATO":
        giocatori_saldati += 1
        partecipanti_saldati += num_p
    elif stato_g == "ACCONTO":
        giocatori_acconto += 1

percentuale = (
    (valore_incassato / valore_totale_atteso)
    if valore_totale_atteso > 0
    else 0
)

if tot_giocatori > 0 and giocatori_saldati == tot_giocatori:
    st.balloons()
    st.success("🎉 **Incassato il 100%!** 🏆")

st.markdown(
    f"<h4 style='margin-top: 10px; font-size: 1.1rem;'>📋 {progetto_selezionato}</h4>",
    unsafe_allow_html=True,
)
st.write(
    f"Quota base: **{quota_unitaria} €** (Acconto: **{val_acconto_u} €** · Pagato/Saldo: **{val_saldo_u} €**)"
)

st.progress(
    percentuale, text=f"Incassato: {int(percentuale * 100)}%"
)

# --- SEZIONE 2: Aggiunta rapida di un giocatore al progetto ---
with st.expander("➕ Aggiungi Giocatore"):
    nuovo_giocatore = st.text_input(
        "Nome e Cognome (es. Mario Rossi)", disabled=not puo_modificare
    )
    if st.button("Aggiungi alla Lista", use_container_width=True, disabled=not puo_modificare):
        if nuovo_giocatore and nuovo_giocatore not in giocatori:
            dati_attivi["giocatori"].append(nuovo_giocatore)
            dati_attivi["giocatori"] = ordina_per_cognome(dati_attivi["giocatori"])
            dati_attivi["pagamenti"][nuovo_giocatore] = record_pagamento_vuoto()
            dati_attivi["partecipanti"][nuovo_giocatore] = 1
            salva_dati(stato_app)
            st.success(f"Aggiunto: {nuovo_giocatore}")
            st.rerun()

# --- SEZIONE 3: Lista interattiva con spunte e metodi Contanti/Bonifico ---
st.markdown("---")
st.markdown(
    f"<p style='color: #64748b; font-size: 0.85em; margin-bottom: 10px;'>Spunte: <b>Acconto ({val_acconto_u}€)</b> e <b>Pagato ({val_saldo_u}€)</b> con metodo <b>Contanti/Bonifico</b> · Stati: <b>IN ATTESA</b>, <b>ACCONTO</b>, <b>PAGATO</b>.</p>",
    unsafe_allow_html=True,
)

if not giocatori:
    st.info("Nessun giocatore in lista. Aggiungine uno sopra.")
else:
    for giocatore in list(giocatori):
        num_part_corrente = partecipanti_dict.get(giocatore, 1)
        (
            inc_g,
            stato_g,
            has_acc,
            has_pag,
            m_acc_corrente,
            m_pag_corrente,
        ) = calcola_quota_giocatore(
            pagamenti_dict.get(giocatore, record_pagamento_vuoto()),
            quota_unitaria,
            num_part_corrente,
        )

        st.markdown(
            '<div class="row-riga-giocatore" style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 3px 4px; margin-bottom: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">',
            unsafe_allow_html=True,
        )

        c_name, c_acc, c_m_acc, c_pag, c_m_pag, c_num, c_badge, c_del = st.columns(
            [1.85, 0.9, 1.25, 0.9, 1.25, 0.68, 1.0, 0.42], gap="small"
        )

        with c_name:
            st.markdown(
                f"<div style='padding-top: 6px; font-weight: 600; font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{giocatore}</div>",
                unsafe_allow_html=True,
            )

        with c_acc:
            nuovo_acc = st.checkbox(
                f"Acc.{val_acconto_u}€",
                value=has_acc,
                key=f"acc_{giocatore}",
                disabled=not puo_modificare,
                help=f"Acconto {val_acconto_u} € a persona",
            )
            if puo_modificare and nuovo_acc != has_acc:
                pagamenti_dict[giocatore] = {
                    "acconto": nuovo_acc,
                    "pagato": has_pag,
                    "metodo_acconto": m_acc_corrente,
                    "metodo_pagato": m_pag_corrente,
                }
                salva_dati(stato_app)
                st.rerun()

        with c_m_acc:
            nuovo_m_acc = st.selectbox(
                f"Metodo acconto {giocatore}",
                options=METODI_PAGAMENTO,
                index=METODI_PAGAMENTO.index(m_acc_corrente),
                key=f"m_acc_{giocatore}",
                disabled=not puo_modificare,
                label_visibility="collapsed",
                help="Metodo pagamento acconto",
            )
            if puo_modificare and nuovo_m_acc != m_acc_corrente:
                pagamenti_dict[giocatore] = {
                    "acconto": has_acc,
                    "pagato": has_pag,
                    "metodo_acconto": nuovo_m_acc,
                    "metodo_pagato": m_pag_corrente,
                }
                salva_dati(stato_app)
                st.rerun()

        with c_pag:
            nuovo_pag = st.checkbox(
                f"Pag.{val_saldo_u}€",
                value=has_pag,
                key=f"pag_{giocatore}",
                disabled=not puo_modificare,
                help=f"Quota/Saldo {val_saldo_u} € a persona",
            )
            if puo_modificare and nuovo_pag != has_pag:
                pagamenti_dict[giocatore] = {
                    "acconto": has_acc,
                    "pagato": nuovo_pag,
                    "metodo_acconto": m_acc_corrente,
                    "metodo_pagato": m_pag_corrente,
                }
                salva_dati(stato_app)
                st.rerun()

        with c_m_pag:
            nuovo_m_pag = st.selectbox(
                f"Metodo saldo {giocatore}",
                options=METODI_PAGAMENTO,
                index=METODI_PAGAMENTO.index(m_pag_corrente),
                key=f"m_pag_{giocatore}",
                disabled=not puo_modificare,
                label_visibility="collapsed",
                help="Metodo pagamento saldo/quota",
            )
            if puo_modificare and nuovo_m_pag != m_pag_corrente:
                pagamenti_dict[giocatore] = {
                    "acconto": has_acc,
                    "pagato": has_pag,
                    "metodo_acconto": m_acc_corrente,
                    "metodo_pagato": nuovo_m_pag,
                }
                salva_dati(stato_app)
                st.rerun()

        with c_num:
            nuovo_num = st.number_input(
                "Persone",
                min_value=1,
                value=num_part_corrente,
                step=1,
                key=f"num_{giocatore}",
                disabled=not puo_modificare,
                label_visibility="collapsed",
            )
            if puo_modificare and nuovo_num != num_part_corrente:
                partecipanti_dict[giocatore] = nuovo_num
                salva_dati(stato_app)
                st.rerun()

        with c_badge:
            if stato_g == "PAGATO":
                st.markdown(
                    "<div style='padding-top: 6px; text-align: center;'><span style='background-color: #d1fae5; color: #065f46; padding: 2px 3px; border-radius: 4px; font-size: 0.56rem; font-weight: 700;'>PAGATO</span></div>",
                    unsafe_allow_html=True,
                )
            elif stato_g == "ACCONTO":
                st.markdown(
                    f"<div style='padding-top: 6px; text-align: center;'><span style='background-color: #fef3c7; color: #92400e; padding: 2px 3px; border-radius: 4px; font-size: 0.56rem; font-weight: 700;'>ACC.{inc_g}€</span></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div style='padding-top: 6px; text-align: center;'><span style='background-color: #fee2e2; color: #991b1b; padding: 2px 3px; border-radius: 4px; font-size: 0.56rem; font-weight: 700;'>ATTESA</span></div>",
                    unsafe_allow_html=True,
                )

        with c_del:
            if st.button(
                "🗑️",
                key=f"del_{giocatore}",
                use_container_width=True,
                disabled=not puo_modificare,
                help=f"Rimuovi {giocatore}",
            ):
                dati_attivi["giocatori"].remove(giocatore)
                if giocatore in dati_attivi["pagamenti"]:
                    del dati_attivi["pagamenti"][giocatore]
                if giocatore in dati_attivi["partecipanti"]:
                    del dati_attivi["partecipanti"][giocatore]
                salva_dati(stato_app)
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# Pulsante esplicito di salvataggio modifiche
st.markdown("<br>", unsafe_allow_html=True)
if st.button(
    "💾 Salva Modifiche",
    type="primary",
    use_container_width=True,
    disabled=not puo_modificare,
):
    salva_dati(stato_app)
    st.toast("✅ Modifiche salvate!", icon="💾")

st.markdown(
    f"<p style='text-align: center; color: #64748b; font-size: 0.78em; margin-top: 4px;'>Ultimo salvataggio: <b>{st.session_state.ultimo_salvataggio}</b></p>",
    unsafe_allow_html=True,
)

# Ricalcolo finale aggiornato
valore_totale_atteso = 0
valore_incassato = 0
giocatori_saldati = 0
giocatori_acconto = 0
partecipanti_saldati = 0

for g in giocatori:
    num_p = partecipanti_dict.get(g, 1)
    valore_totale_atteso += quota_unitaria * num_p
    inc_g, stato_g, _, _, _, _ = calcola_quota_giocatore(
        pagamenti_dict.get(g, record_pagamento_vuoto()),
        quota_unitaria,
        num_p,
    )
    valore_incassato += inc_g
    if stato_g == "PAGATO":
        giocatori_saldati += 1
        partecipanti_saldati += num_p
    elif stato_g == "ACCONTO":
        giocatori_acconto += 1

# --- SEZIONE 4: Riepilogo Finanziario, Esportazione CSV e Backup JSON ---
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### 📊 Riepilogo Finanziario")

m1, m2, m3 = st.columns(3)
m1.metric(
    "Saldati / Acconti",
    f"{giocatori_saldati} saldati · {giocatori_acconto} acconti su {tot_giocatori}",
)
m2.metric("Incassato", f"{valore_incassato} €")
m3.metric("Mancante", f"{valore_totale_atteso - valore_incassato} €")

st.markdown("<br>", unsafe_allow_html=True)

csv_data = genera_csv(progetto_selezionato, dati_attivi)
nome_file_safe = (
    progetto_selezionato.lower()
    .replace(" ", "_")
    .replace("(", "")
    .replace(")", "")
)

st.download_button(
    label="📥 Scarica Report CSV (.csv)",
    data=csv_data,
    file_name=f"report_{nome_file_safe}.csv",
    mime="text/csv",
    use_container_width=True,
)

with st.expander("💾 Backup e Ripristino Dati (JSON)"):
    st.markdown(
        "<p style='color: #64748b; font-size: 0.85em;'>Scarica il file JSON per trasferire i dati su un altro dispositivo o caricalo per ripristinare uno stato precedente.</p>",
        unsafe_allow_html=True,
    )

    json_bytes = serializza_json(stato_app)
    st.download_button(
        label="📥 Scarica Backup JSON (.json)",
        data=json_bytes,
        file_name=FILE_DATI,
        mime="application/json",
        use_container_width=True,
    )

    file_caricato = st.file_uploader(
        "Carica file di backup (.json)",
        type=["json"],
        key="uploader_backup_json",
        disabled=not puo_modificare,
    )

    if file_caricato is not None and puo_modificare:
        if st.button("📤 Ripristina Dati da JSON", use_container_width=True):
            try:
                contenuto_testo = file_caricato.getvalue().decode("utf-8")
                dati_importati = json.loads(contenuto_testo)
                nuovo_stato = normalizza_stato_completo(dati_importati)
                st.session_state.stato_app = nuovo_stato
                if st.session_state.utente_attivo not in nuovo_stato["utenti"]:
                    st.session_state.autenticato = False
                    st.session_state.utente_attivo = None
                salva_dati(nuovo_stato)
                st.success("Backup JSON importato e salvato correttamente!")
                st.rerun()
            except Exception as e:
                st.error(f"Impossibile importare il file JSON: {e}")

# --- SEZIONE 5: Generatore Messaggio WhatsApp per Promemoria ---
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("📱 Genera Promemoria WhatsApp"):
    st.markdown(
        "<p style='color: #64748b; font-size: 0.85em;'>Crea un promemoria con chi è in attesa o ha versato solo l'acconto.</p>",
        unsafe_allow_html=True,
    )

    non_saldati = []
    for g in giocatori:
        num_p = partecipanti_dict.get(g, 1)
        dovuto_g = quota_unitaria * num_p
        inc_g, stato_g, has_a, has_p, m_a, m_p = calcola_quota_giocatore(
            pagamenti_dict.get(g, record_pagamento_vuoto()),
            quota_unitaria,
            num_p,
        )
        residuo_g = max(0, dovuto_g - inc_g)
        if residuo_g > 0:
            non_saldati.append((g, num_p, stato_g, inc_g, residuo_g, has_a, m_a))

    if not non_saldati:
        st.success("Tutti in regola! Nessun promemoria da inviare. 🎉")
    else:
        testo_msg = "⚽ *USO Nuvolento - Promemoria Quote*\n"
        testo_msg += f"Progetto: *{progetto_selezionato}*\n\n"
        testo_msg += "Risultano ancora da completare le seguenti quote:\n"

        totale_residuo = 0
        for g, num_pers, stato_g, inc_g, residuo_g, has_a, m_a in non_saldati:
            totale_residuo += residuo_g
            dettaglio_acc = f" · Acc. {m_a}" if has_a else ""
            testo_msg += (
                f"• {g} (Pers: {num_pers} · {stato_g}{dettaglio_acc} · Versati: {inc_g} € · Residuo: {residuo_g} €)\n"
            )

        testo_msg += f"\nTotale residuo da incassare: *{totale_residuo} €*\n"
        testo_msg += "Vi invitiamo a regolarizzare la posizione. Grazie! 🔴🔵"

        messaggio_finale = st.text_area(
            "Testo WhatsApp:", value=testo_msg, height=180
        )

        encoded_msg = urllib.parse.quote(messaggio_finale)
        whatsapp_url = f"https://wa.me/?text={encoded_msg}"

        st.markdown(
            f'<a href="{whatsapp_url}" target="_blank"><button style="width:100%; background-color:#25d366; color:white; border:none; padding:12px 20px; border-radius:8px; font-weight:600; cursor:pointer; text-align:center;">💬 Apri su WhatsApp</button></a>',
            unsafe_allow_html=True,
        )
