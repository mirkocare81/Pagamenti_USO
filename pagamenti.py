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

import io
import json
import os
import urllib.parse
import pandas as pd
import streamlit as st

# Configurazione della pagina
st.set_page_config(
    page_title="Gestione Incassi - USO Nuvolento", page_icon="⚽", layout="centered"
)

# --- GESTIONE PERSISTENZA DATI (FILE JSON) ---
FILE_DATI = "dati_pagamenti.json"


def ordina_per_cognome(lista_giocatori):
    return sorted(
        lista_giocatori,
        key=lambda x: x.split(" ", 1)[1] if " " in x else x,
    )


def carica_dati():
    if os.path.exists(FILE_DATI):
        try:
            with open(FILE_DATI, "r", encoding="utf-8") as f:
                dati = json.load(f)
                for proj in dati.values():
                    if "giocatori" in proj:
                        proj["giocatori"] = ordina_per_cognome(proj["giocatori"])
                        if "partecipanti" not in proj:
                            proj["partecipanti"] = {
                                g: 1 for g in proj["giocatori"]
                            }
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

    return {
        "Torneo Lignano Sabbiadoro (Under 16 - 2011)": {
            "quota": 260,
            "giocatori": giocatori_ordinati,
            "pagamenti": {},
            "partecipanti": partecipanti_iniziali,
        }
    }


def salva_dati(progetti):
    with open(FILE_DATI, "w", encoding="utf-8") as f:
        json.dump(progetti, f, ensure_ascii=False, indent=4)


# --- FUNZIONE PER ESPORTARE IN EXCEL ---
def genera_excel(progetto_nome, dati_progetto):
    output = io.BytesIO()
    giocatori = dati_progetto["giocatori"]
    pagamenti = dati_progetto["pagamenti"]
    partecipanti = dati_progetto.get("partecipanti", {})
    quota = dati_progetto["quota"]

    data_list = []
    for g in giocatori:
        ha_pagato = pagamenti.get(g, False)
        num_persone = partecipanti.get(g, 1)
        totale_dovuto = quota * num_persone
        totale_pagato = totale_dovuto if ha_pagato else 0

        data_list.append(
            {
                "Giocatore": g,
                "Partecipanti al seguito": num_persone,
                "Stato Pagamento": "PAGATO" if ha_pagato else "IN ATTESA",
                "Quota Unitaria (€)": quota,
                "Totale Dovuto (€)": totale_dovuto,
                "Totale Incassato (€)": totale_pagato,
            }
        )

    df = (
        pd.DataFrame(data_list)
        if data_list
        else pd.DataFrame(
            columns=[
                "Giocatore",
                "Partecipanti al seguito",
                "Stato Pagamento",
                "Quota Unitaria (€)",
                "Totale Dovuto (€)",
                "Totale Incassato (€)",
            ]
        )
    )

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Report Pagamenti")

    return output.getvalue()


# --- CSS PERSONALIZZATO (SFONDO CHIARO E SCRITTE SCURE SENZA TAGLI) ---
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
        
        .stButton button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        button[kind="primary"] {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            border: none;
            color: white !important;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.2);
        }
        button[kind="primary"]:hover {
            background: linear-gradient(135deg, #059669 0%, #047857 100%);
            box-shadow: 0 6px 16px rgba(16, 185, 129, 0.4);
        }
        
        /* Ottimizzazione dei box totali per evitare tagli di testo */
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            padding: 12px 15px;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            height: auto !important;
            min-height: 95px;
        }
        div[data-testid="stMetric"] label {
            color: #64748b !important;
            font-weight: 500;
            white-space: normal !important;
            word-break: break-word !important;
            font-size: 0.85rem !important;
        }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: #0f172a !important;
            font-weight: 700;
            white-space: normal !important;
            word-break: break-word !important;
            font-size: 1.05rem !important;
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
    </style>
""",
    unsafe_allow_html=True,
)

# Inizializzazione dello stato caricando dal file JSON
if "progetti" not in st.session_state:
    st.session_state.progetti = carica_dati()

for proj_name, data in st.session_state.progetti.items():
    if "partecipanti" not in data:
        data["partecipanti"] = {}
    for g in data["giocatori"]:
        if g not in data["pagamenti"]:
            data["pagamenti"][g] = False
        if g not in data["partecipanti"]:
            data["partecipanti"][g] = 1

# Intestazione App
st.markdown(
    "<h1 style='text-align: center; margin-bottom: 0;'>⚽ Gestione Incassi Tornei</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align: center; color: #64748b; margin-top: 5px;'>USO Nuvolento - Monitoraggio Quote Squadra</p>",
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
    with st.popover("➕ Nuovo Progetto", use_container_width=True):
        nuovo_nome = st.text_input("Nome Progetto")
        nuova_quota = st.number_input(
            "Quota a persona (€)", min_value=0, value=260, step=10
        )
        if st.button("Crea Progetto", use_container_width=True):
            if nuovo_nome and nuovo_nome not in st.session_state.progetti:
                st.session_state.progetti[nuovo_nome] = {
                    "quota": nuova_quota,
                    "giocatori": [],
                    "pagamenti": {},
                    "partecipanti": {},
                }
                salva_dati(st.session_state.progetti)
                st.success(f"Progetto '{nuovo_nome}' creato!")
                st.rerun()

dati_attivi = st.session_state.progetti[progetto_selezionato]
quota_unitaria = dati_attivi["quota"]
giocatori = dati_attivi["giocatori"]
pagamenti_dict = dati_attivi["pagamenti"]
partecipanti_dict = dati_attivi["partecipanti"]
tot_giocatori = len(giocatori)

# Calcoli finanziari e conteggi
valore_totale_atteso = sum(
    quota_unitaria * partecipanti_dict.get(g, 1) for g in giocatori
)
valore_incassato = sum(
    quota_unitaria * partecipanti_dict.get(g, 1)
    for g in giocatori
    if pagamenti_dict.get(g, False)
)
spunte_attuali = sum(1 for g in giocatori if pagamenti_dict.get(g, False))

totale_partecipanti_teorico = sum(partecipanti_dict.get(g, 1) for g in giocatori)
partecipanti_paganti = sum(
    partecipanti_dict.get(g, 1) for g in giocatori if pagamenti_dict.get(g, False)
)

percentuale = (
    (spunte_attuali / tot_giocatori) if tot_giocatori > 0 else 0
)

if tot_giocatori > 0 and spunte_attuali == tot_giocatori:
    st.balloons()
    st.success("🎉 **Ben fatto, hai incassato il 100%!** 🏆")

st.markdown(
    f"<h4 style='margin-top: 15px;'>📋 {progetto_selezionato}</h4>",
    unsafe_allow_html=True,
)
st.write(f"Quota individuale base: **{quota_unitaria} €**")

st.progress(
    percentuale, text=f"Progresso incassi giocatori: {int(percentuale * 100)}%"
)

# --- SEZIONE 2: Aggiunta rapida di un giocatore al progetto ---
with st.expander("➕ Aggiungi un nuovo giocatore alla lista"):
    nuovo_giocatore = st.text_input("Nome e Cognome del giocatore (es. Mario Rossi)")
    if st.button("Aggiungi Giocatore alla Lista"):
        if nuovo_giocatore and nuovo_giocatore not in giocatori:
            dati_attivi["giocatori"].append(nuovo_giocatore)
            dati_attivi["giocatori"] = ordina_per_cognome(dati_attivi["giocatori"])
            dati_attivi["pagamenti"][nuovo_giocatore] = False
            dati_attivi["partecipanti"][nuovo_giocatore] = 1
            salva_dati(st.session_state.progetti)
            st.success(f"Aggiunto e ordinato: {nuovo_giocatore}")
            st.rerun()

# --- SEZIONE 3: Lista interattiva con partecipanti e salvataggio automatico ---
st.markdown("---")
st.markdown(
    "<p style='color: #64748b; font-size: 0.9em; margin-bottom: 15px;'>Imposta le persone al seguito e spunta i pagamenti: ogni modifica è salvata in tempo reale.</p>",
    unsafe_allow_html=True,
)

if not giocatori:
    st.info(
        "Nessun giocatore in lista. Aggiungine uno usando il menu a tendina qui sopra."
    )
else:
    for giocatore in list(giocatori):
        is_pagato = pagamenti_dict.get(giocatore, False)
        num_part_corrente = partecipanti_dict.get(giocatore, 1)

        col_chk, col_num, col_badge, col_del = st.columns([2.2, 1.2, 1, 1])

        with col_chk:
            nuovo_stato = st.checkbox(
                f"{giocatore}", value=is_pagato, key=f"chk_{giocatore}"
            )
            if nuovo_stato != is_pagato:
                pagamenti_dict[giocatore] = nuovo_stato
                salva_dati(st.session_state.progetti)
                st.rerun()

        with col_num:
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

        with col_badge:
            if is_pagato:
                st.markdown(
                    "<span style='background-color: #d1fae5; color: #065f46; padding: 4px 8px; border-radius: 6px; font-size: 0.75em; font-weight: 600;'>PAGATO</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<span style='background-color: #fee2e2; color: #991b1b; padding: 4px 8px; border-radius: 6px; font-size: 0.75em; font-weight: 600;'>IN ATTESA</span>",
                    unsafe_allow_html=True,
                )

        with col_del:
            if st.button("🗑️ Rimuovi", key=f"del_{giocatore}", use_container_width=True):
                dati_attivi["giocatori"].remove(giocatore)
                if giocatore in dati_attivi["pagamenti"]:
                    del dati_attivi["pagamenti"][giocatore]
                if giocatore in dati_attivi["partecipanti"]:
                    del dati_attivi["partecipanti"][giocatore]
                salva_dati(st.session_state.progetti)
                st.success(f"Rimosso: {giocatore}")
                st.rerun()

# Ricalcolo finale aggiornato
valore_totale_atteso = sum(
    quota_unitaria * partecipanti_dict.get(g, 1) for g in giocatori
)
valore_incassato = sum(
    quota_unitaria * partecipanti_dict.get(g, 1)
    for g in giocatori
    if pagamenti_dict.get(g, False)
)

# --- SEZIONE 4: Riepilogo Finanziario ed Esportazione ---
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### 📊 Riepilogo Finanziario")

m1, m2, m3 = st.columns(3)
m1.metric(
    "Giocatori / Partecipanti", 
    f"{spunte_attuali}/{tot_giocatori} ({partecipanti_paganti}/{totale_partecipanti_teorico} pers.)"
)
m2.metric("Incassato", f"{valore_incassato} €")
m3.metric("Mancante", f"{valore_totale_atteso - valore_incassato} €")

st.markdown("<br>", unsafe_allow_html=True)

excel_data = genera_excel(progetto_selezionato, dati_attivi)
nome_file_safe = (
    progetto_selezionato.lower()
    .replace(" ", "_")
    .replace("(", "")
    .replace(")", "")
)

st.download_button(
    label="📥 Scarica Report in Excel (.xlsx)",
    data=excel_data,
    file_name=f"report_{nome_file_safe}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

# --- SEZIONE 5: Generatore Messaggio WhatsApp per Promemoria ---
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("📱 Genera Messaggio WhatsApp Promemoria"):
    st.markdown(
        "<p style='color: #64748b; font-size: 0.9em;'>Crea un promemoria precompilato con l'elenco di chi non ha ancora saldato la quota per il progetto attivo.</p>",
        unsafe_allow_html=True,
    )

    non_pagati = [
        g for g in giocatori if not pagamenti_dict.get(g, False)
    ]

    if not non_pagati:
        st.success(
            "Ottimo! Tutti i giocatori in elenco hanno saldato il pagamento. Non ci sono promemoria da inviare! 🎉"
        )
    else:
        testo_msg = f"⚽ *USO Nuvolento - Promemoria Quote*\n"
        testo_msg += f"Progetto: *{progetto_selezionato}*\n\n"
        testo_msg += (
            "Si ricorda che risultano ancora in attesa di saldo le quote per:\n"
        )

        totale_da_incassare_rimanente = 0
        for g in non_pagati:
            num_pers = partecipanti_dict.get(g, 1)
            dovuto = quota_unitaria * num_pers
            totale_da_incassare_rimanente += dovuto
            testo_msg += f"• {g} (Persone: {num_pers} - Tot: {dovuto} €)\n"

        testo_msg += (
            f"\nTotale da raccogliere: *{totale_da_incassare_rimanente} €*\n"
        )
        testo_msg += "Vi invitiamo a regolarizzare la posizione il prima possibile. Grazie per la collaborazione! 🔴🔵"

        messaggio_finale = st.text_area(
            "Anteprima messaggio WhatsApp:", value=testo_msg, height=220
        )

        encoded_msg = urllib.parse.quote(messaggio_finale)
        whatsapp_url = f"https://wa.me/?text={encoded_msg}"

        col_wa1, col_wa2 = st.columns(2)
        with col_wa1:
            st.markdown(
                f'<a href="{whatsapp_url}" target="_blank"><button style="width:100%; background-color:#25d366; color:white; border:none; padding:10px 20px; border-radius:8px; font-weight:600; cursor:pointer;">💬 Apri su WhatsApp</button></a>',
                unsafe_allow_html=True,
            )
        with col_wa2:
            st.info(
                "💡 Puoi copiare il testo qui sopra o cliccare direttamente per inviarlo."
            )
