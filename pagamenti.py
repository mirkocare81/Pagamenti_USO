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


def calcola_quota_giocatore(stato_record, quota_unitaria, num_persone):
    """Restituisce (importo_incassato, stato_testo, has_acconto, has_pagato)."""
    if isinstance(stato_record, dict):
        has_acconto = bool(stato_record.get("acconto", False))
        has_pagato = bool(stato_record.get("pagato", False))
    else:
        has_acconto = False
        has_pagato = bool(stato_record)

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

    return importo_incassato, stato, has_acconto, has_pagato


def carica_dati():
    if os.path.exists(FILE_DATI):
        try:
            with open(FILE_DATI, "r", encoding="utf-8") as f:
                dati = json.load(f)
                if isinstance(dati, dict) and dati:
                    for proj in dati.values():
                        if "giocatori" in proj:
                            proj["giocatori"] = ordina_per_cognome(
                                proj["giocatori"]
                            )
                            if "partecipanti" not in proj:
                                proj["partecipanti"] = {
                                    g: 1 for g in proj["giocatori"]
                                }
                            if "pagamenti" not in proj:
                                proj["pagamenti"] = {}
                    return dati
        except Exception:
            pass

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
        g: {"acconto": False, "pagato": False} for g in giocatori_ordinati
    }

    return {
        "Torneo Lignano Sabbiadoro (Under 16 - 2011)": {
            "quota": 260,
            "giocatori": giocatori_ordinati,
            "pagamenti": pagamenti_iniziali,
            "partecipanti": partecipanti_iniziali,
        }
    }


def salva_dati(progetti):
    with open(FILE_DATI, "w", encoding="utf-8") as f:
        json.dump(progetti, f, ensure_ascii=False, indent=4)
    st.session_state.ultimo_salvataggio = datetime.now().strftime("%H:%M:%S")


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
        totale_pagato, stato, has_acconto, has_pagato = calcola_quota_giocatore(
            pagamenti.get(g, {"acconto": False, "pagato": False}),
            quota,
            num_persone,
        )

        data_list.append(
            {
                "Giocatore": g,
                "Partecipanti al seguito": num_persone,
                "Acconto (100€)": "SI" if has_acconto else "NO",
                "Pagato (160€)": "SI" if has_pagato else "NO",
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
                "Pagato (160€)",
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
            gap: 4px !important;
        }

        [data-testid="stColumn"] {
            min-width: 0 !important;
            flex: 1 1 auto !important;
        }

        .stButton button {
            border-radius: 6px;
            font-weight: 600;
            min-height: 32px;
            max-height: 38px;
            padding: 0px 6px !important;
            font-size: 0.8rem;
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
            border-radius: 8px !important;
            border-color: #cbd5e1 !important;
        }

        @media (max-width: 640px) {
            .block-container {
                padding-left: 4px !important;
                padding-right: 4px !important;
                padding-top: 15px !important;
            }
            h1 {
                font-size: 1.4rem !important;
            }
        }
    </style>
""",
    unsafe_allow_html=True,
)

# Inizializzazione dello stato caricando dal file JSON
if "progetti" not in st.session_state:
    st.session_state.progetti = carica_dati()

if "ultimo_salvataggio" not in st.session_state:
    st.session_state.ultimo_salvataggio = (
        datetime.now().strftime("%H:%M:%S")
        if os.path.exists(FILE_DATI)
        else "Non ancora salvato"
    )

for proj_name, data in st.session_state.progetti.items():
    if "partecipanti" not in data:
        data["partecipanti"] = {}
    if "pagamenti" not in data:
        data["pagamenti"] = {}
    for g in data["giocatori"]:
        if g not in data["pagamenti"]:
            data["pagamenti"][g] = {"acconto": False, "pagato": False}
        elif not isinstance(data["pagamenti"][g], dict):
            vecchio_bool = bool(data["pagamenti"][g])
            data["pagamenti"][g] = {
                "acconto": False,
                "pagato": vecchio_bool,
            }
        if g not in data["partecipanti"]:
            data["partecipanti"][g] = 1

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

# --- SEZIONE 1: Gestione Progetti e Selezione ---
st.markdown("### 📁 Progetto Attivo")

col_sel, col_add = st.columns([2, 1])

with col_sel:
    lista_progetti = list(st.session_state.progetti.keys())
    progetto_selezionato = st.selectbox(
        "Progetto attivo", lista_progetti, label_visibility="collapsed"
    )

with col_add:
    with st.popover("➕ Nuovo", use_container_width=True):
        nuovo_nome = st.text_input("Nome Progetto")
        nuova_quota = st.number_input(
            "Quota (€)", min_value=0, value=260, step=10
        )
        if st.button("Crea", use_container_width=True):
            if nuovo_nome and nuovo_nome not in st.session_state.progetti:
                st.session_state.progetti[nuovo_nome] = {
                    "quota": nuova_quota,
                    "giocatori": [],
                    "pagamenti": {},
                    "partecipanti": {},
                }
                salva_dati(st.session_state.progetti)
                st.success(f"'{nuovo_nome}' creato!")
                st.rerun()

dati_attivi = st.session_state.progetti[progetto_selezionato]
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
    inc_g, stato_g, _, _ = calcola_quota_giocatore(
        pagamenti_dict.get(g, {"acconto": False, "pagato": False}),
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
    nuovo_giocatore = st.text_input("Nome e Cognome (es. Mario Rossi)")
    if st.button("Aggiungi alla Lista", use_container_width=True):
        if nuovo_giocatore and nuovo_giocatore not in giocatori:
            dati_attivi["giocatori"].append(nuovo_giocatore)
            dati_attivi["giocatori"] = ordina_per_cognome(dati_attivi["giocatori"])
            dati_attivi["pagamenti"][nuovo_giocatore] = {
                "acconto": False,
                "pagato": False,
            }
            dati_attivi["partecipanti"][nuovo_giocatore] = 1
            salva_dati(st.session_state.progetti)
            st.success(f"Aggiunto: {nuovo_giocatore}")
            st.rerun()

# --- SEZIONE 3: Lista interattiva con spunte Acconto (100€) e Pagato (160€) ---
st.markdown("---")
st.markdown(
    f"<p style='color: #64748b; font-size: 0.85em; margin-bottom: 10px;'>Spunte: <b>Acconto ({val_acconto_u}€)</b> e <b>Pagato ({val_saldo_u}€)</b> · Stati: <b>IN ATTESA</b>, <b>ACCONTO</b>, <b>PAGATO</b>.</p>",
    unsafe_allow_html=True,
)

if not giocatori:
    st.info("Nessun giocatore in lista. Aggiungine uno sopra.")
else:
    for giocatore in list(giocatori):
        num_part_corrente = partecipanti_dict.get(giocatore, 1)
        inc_g, stato_g, has_acc, has_pag = calcola_quota_giocatore(
            pagamenti_dict.get(giocatore, {"acconto": False, "pagato": False}),
            quota_unitaria,
            num_part_corrente,
        )

        st.markdown(
            '<div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 4px 6px; margin-bottom: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">',
            unsafe_allow_html=True,
        )

        c_name, c_acc, c_pag, c_num, c_badge, c_del = st.columns(
            [2.6, 1.1, 1.1, 0.9, 1.1, 0.5], gap="small"
        )

        with c_name:
            st.markdown(
                f"<div style='padding-top: 6px; font-weight: 600; font-size: 0.85rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{giocatore}</div>",
                unsafe_allow_html=True,
            )

        with c_acc:
            nuovo_acc = st.checkbox(
                f"Acc. {val_acconto_u}€",
                value=has_acc,
                key=f"acc_{giocatore}",
                help=f"Acconto {val_acconto_u} € a persona",
            )
            if nuovo_acc != has_acc:
                pagamenti_dict[giocatore] = {
                    "acconto": nuovo_acc,
                    "pagato": has_pag,
                }
                salva_dati(st.session_state.progetti)
                st.rerun()

        with c_pag:
            nuovo_pag = st.checkbox(
                f"Pag. {val_saldo_u}€",
                value=has_pag,
                key=f"pag_{giocatore}",
                help=f"Quota/Saldo {val_saldo_u} € a persona",
            )
            if nuovo_pag != has_pag:
                pagamenti_dict[giocatore] = {
                    "acconto": has_acc,
                    "pagato": nuovo_pag,
                }
                salva_dati(st.session_state.progetti)
                st.rerun()

        with c_num:
            nuovo_num = st.number_input(
                "Persone",
                min_value=1,
                value=num_part_corrente,
                step=1,
                key=f"num_{giocatore}",
                label_visibility="collapsed",
            )
            if nuovo_num != num_part_corrente:
                partecipanti_dict[giocatore] = nuovo_num
                salva_dati(st.session_state.progetti)
                st.rerun()

        with c_badge:
            if stato_g == "PAGATO":
                st.markdown(
                    "<div style='padding-top: 6px; text-align: center;'><span style='background-color: #d1fae5; color: #065f46; padding: 2px 4px; border-radius: 4px; font-size: 0.6em; font-weight: 700;'>PAGATO</span></div>",
                    unsafe_allow_html=True,
                )
            elif stato_g == "ACCONTO":
                st.markdown(
                    f"<div style='padding-top: 6px; text-align: center;'><span style='background-color: #fef3c7; color: #92400e; padding: 2px 4px; border-radius: 4px; font-size: 0.6em; font-weight: 700;'>ACCONTO ({inc_g}€)</span></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div style='padding-top: 6px; text-align: center;'><span style='background-color: #fee2e2; color: #991b1b; padding: 2px 4px; border-radius: 4px; font-size: 0.6em; font-weight: 700;'>IN ATTESA</span></div>",
                    unsafe_allow_html=True,
                )

        with c_del:
            if st.button(
                "🗑️",
                key=f"del_{giocatore}",
                use_container_width=True,
                help=f"Rimuovi {giocatore}",
            ):
                dati_attivi["giocatori"].remove(giocatore)
                if giocatore in dati_attivi["pagamenti"]:
                    del dati_attivi["pagamenti"][giocatore]
                if giocatore in dati_attivi["partecipanti"]:
                    del dati_attivi["partecipanti"][giocatore]
                salva_dati(st.session_state.progetti)
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# Pulsante esplicito di salvataggio modifiche
st.markdown("<br>", unsafe_allow_html=True)
if st.button("💾 Salva Modifiche", type="primary", use_container_width=True):
    salva_dati(st.session_state.progetti)
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
    inc_g, stato_g, _, _ = calcola_quota_giocatore(
        pagamenti_dict.get(g, {"acconto": False, "pagato": False}),
        quota_unitaria,
        num_p,
    )
    valore_incassato += inc_g
    if stato_g == "PAGATO":
        giocatori_saldati += 1
        partecipanti_saldati += num_p
    elif stato_g == "ACCONTO":
        giocatori_acconto += 1

# --- SEZIONE 4: Riepilogo Finanziario ed Esportazione CSV ---
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
        inc_g, stato_g, _, _ = calcola_quota_giocatore(
            pagamenti_dict.get(g, {"acconto": False, "pagato": False}),
            quota_unitaria,
            num_p,
        )
        residuo_g = max(0, dovuto_g - inc_g)
        if residuo_g > 0:
            non_saldati.append((g, num_p, stato_g, inc_g, residuo_g))

    if not non_saldati:
        st.success("Tutti in regola! Nessun promemoria da inviare. 🎉")
    else:
        testo_msg = "⚽ *USO Nuvolento - Promemoria Quote*\n"
        testo_msg += f"Progetto: *{progetto_selezionato}*\n\n"
        testo_msg += "Risultano ancora da completare le seguenti quote:\n"

        totale_residuo = 0
        for g, num_pers, stato_g, inc_g, residuo_g in non_saldati:
            totale_residuo += residuo_g
            testo_msg += (
                f"• {g} (Pers: {num_pers} · {stato_g} · Versati: {inc_g} € · Residuo: {residuo_g} €)\n"
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
