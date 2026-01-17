import streamlit as st
import pandas as pd
import plotly.express as px
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from gedcom.element.individual import IndividualElement
from gedcom.parser import Parser
import re
import tempfile
import os

# --- SIVUN ASETUKSET ---
st.set_page_config(page_title="Suku Kartalla", layout="wide")

st.title("📍 Sukututkimusdata Kartalla")
st.markdown("""
Tämä sovellus lukee **GEDCOM-tiedoston**, poimii henkilöiden syntymäpaikat ja
visualisoi ne aikajanalla Suomen kartalle.
""")

# --- APUFUNKTIOT ---

def get_year_from_date(date_str):
    """Etsii ensimmäisen 4-numeroisen luvun merkkijonosta."""
    if not date_str:
        return None
    match = re.search(r'\d{4}', date_str)
    return int(match.group(0)) if match else None

@st.cache_data
def parse_gedcom(file_content):
    """
    Lukee GEDCOM-datan ja palauttaa Pandasin DataFramen.
    Sisältää nyt automaattisen koodauksen korjauksen (UTF-8 / Latin-1).
    """
    
    # --- 1. Koodauksen korjaus ---
    decoded_text = ""
    try:
        # Yritetään ensin UTF-8 (standardi)
        decoded_text = file_content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            # Jos ei onnistu, yritetään Latin-1 (yleinen Windows/Suomi vanhoissa tiedostoissa)
            decoded_text = file_content.decode('latin-1')
        except Exception:
            # Jos mikään ei toimi, pakotetaan luku jättämällä virheet huomiotta
            decoded_text = file_content.decode('utf-8', errors='ignore')

    # --- 2. Kirjoitetaan puhdas UTF-8 väliaikaiseen tiedostoon ---
    # Avataan tiedosto tekstitilassa ('w') ja pakotetaan encoding='utf-8'
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ged", mode='w', encoding='utf-8') as tmp_file:
        tmp_file.write(decoded_text)
        tmp_path = tmp_file.name

    # --- 3. Jäsennys ---
    try:
        gedcom_parser = Parser()
        gedcom_parser.parse_file(tmp_path)
        
        root_child_elements = gedcom_parser.get_root_child_elements()
        data = []

        for element in root_child_elements:
            if isinstance(element, IndividualElement):
                try:
                    name_tuple = element.get_name()
                    first = name_tuple[0] if name_tuple[0] else ""
                    last = name_tuple[1] if name_tuple[1] else ""
                    full_name = f"{first} {last}".strip()

                    birth_data = element.get_birth_data()
                    
                    if birth_data and birth_data[1]: # Jos paikka löytyy
                        birth_date = birth_data[0]
                        birth_place = birth_data[1]
                        birth_year = get_year_from_date(birth_date)

                        if birth_year and birth_place:
                            data.append({
                                "Nimi": full_name,
                                "Syntymäaika": birth_date,
                                "Vuosi": birth_year,
                                "Paikka": birth_place
                            })
                except Exception:
                    continue 
                    
    finally:
        # Siivotaan väliaikainen tiedosto
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    
    return pd.DataFrame(data)

@st.cache_data
def geocode_dataframe(df):
    """
    Hakee koordinaatit paikoille. 
    Tämä on välimuistissa, jotta hidasta hakua ei tehdä turhaan uudestaan.
    """
    geolocator = Nominatim(user_agent="streamlit_family_map_v1")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1) 
    
    unique_places = df['Paikka'].unique()
    place_coords = {}
    
    # Luodaan edistymispalkki
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(unique_places)
    
    for i, place in enumerate(unique_places):
        # Päivitetään palkkia
        progress = (i + 1) / total
        progress_bar.progress(progress)
        status_text.text(f"Haetaan koordinaatteja: {place} ({i+1}/{total})")
        
        # Lisätään hakuun maa, jos se puuttuu
        query = place
        if "finland" not in place.lower() and "suomi" not in place.lower():
            query = f"{place}, Finland"
            
        try:
            location = geocode(query)
            if location:
                place_coords[place] = (location.latitude, location.longitude)
            else:
                place_coords[place] = (None, None)
        except Exception:
            place_coords[place] = (None, None)
            
    status_text.empty()
    progress_bar.empty()
    
    # Mapataan koordinaatit DataFrameen
    df['lat'] = df['Paikka'].map(lambda x: place_coords.get(x, (None, None))[0])
    df['lon'] = df['Paikka'].map(lambda x: place_coords.get(x, (None, None))[1])
    
    return df.dropna(subset=['lat', 'lon'])

# --- KÄYTTÖLIITTYMÄ JA LOGIIKKA ---

uploaded_file = st.file_uploader("Lataa GEDCOM-tiedosto (.ged)", type=['ged'])

if uploaded_file is not None:
    st.info("Tiedosto ladattu. Käsitellään dataa...")
    
    # 1. Jäsennä tiedosto
    bytes_data = uploaded_file.getvalue()
    df = parse_gedcom(bytes_data)
    
    if df.empty:
        st.error("Tiedostosta ei löytynyt sopivia syntymätietoja. Tarkista tiedosto.")
    else:
        st.success(f"Löydettiin {len(df)} henkilöä, joilla on syntymäaika ja -paikka.")
        
        # 2. Geokoodaus (vain jos käyttäjä painaa nappia)
        if st.button("Hae koordinaatit ja piirrä kartta"):
            with st.spinner('Haetaan sijaintitietoja... Tämä voi kestää hetken.'):
                df_geo = geocode_dataframe(df)
            
            if df_geo.empty:
                st.warning("Koordinaatteja ei löytynyt.")
            else:
                st.success(f"Koordinaatit löytyi {len(df_geo)} tapahtumalle!")
                
                # Järjestys animaatiota varten
                df_geo = df_geo.sort_values("Vuosi")
                
                # 3. Piirrä kartta
                fig = px.scatter_mapbox(
                    df_geo,
                    lat="lat",
                    lon="lon",
                    hover_name="Nimi",
                    hover_data={"Syntymäaika": True, "Paikka": True, "lat": False, "lon": False, "Vuosi": False},
                    color_discrete_sequence=['blue'], 
                    zoom=4.5,
                    center={"lat": 64.5, "lon": 26.0},
                    animation_frame="Vuosi",
                    title=f"Syntymät aikajanalla ({df_geo['Vuosi'].min()} - {df_geo['Vuosi'].max()})",
                    size_max=15
                )

                fig.update_layout(mapbox_style="open-street-map")
                fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
                
                st.plotly_chart(fig, use_container_width=True)
                
                with st.expander("Katso raakadata"):
                    st.dataframe(df_geo)
