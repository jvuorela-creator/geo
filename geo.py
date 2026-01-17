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

# --- 1. ASETUKSET (Tämän pitää olla AINA ensimmäinen komento) ---
st.set_page_config(page_title="Suku Kartalla", layout="wide")

# --- 2. APUFUNKTIOT ---

def get_year_from_date(date_str):
    if not date_str:
        return None
    match = re.search(r'\d{4}', str(date_str))
    return int(match.group(0)) if match else None

@st.cache_data
def parse_gedcom(file_content):
    """Lukee GEDCOM-tiedoston ja etsii syntymätiedot."""
    # Koodauksen korjaus
    decoded_text = ""
    try:
        decoded_text = file_content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            decoded_text = file_content.decode('latin-1')
        except Exception:
            decoded_text = file_content.decode('utf-8', errors='ignore')

    # Siivotaan tyhjät rivit
    lines = decoded_text.splitlines()
    clean_lines = [line for line in lines if line.strip()]
    cleaned_text = "\n".join(clean_lines)

    # Väliaikainen tiedosto
    tmp_path = ""
    data = []
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ged", mode='w', encoding='utf-8') as tmp_file:
            tmp_file.write(cleaned_text)
            tmp_path = tmp_file.name

        # Parsitaan (strict=False)
        gedcom_parser = Parser()
        gedcom_parser.parse_file(tmp_path, strict=False)
        
        root_child_elements = gedcom_parser.get_root_child_elements()

        # Käydään läpi henkilöt
        for element in root_child_elements:
            if isinstance(element, IndividualElement):
                try:
                    # Nimi
                    name_tuple = element.get_name()
                    first = name_tuple[0] if name_tuple[0] else ""
                    last = name_tuple[1] if name_tuple[1] else ""
                    full_name = f"{first} {last}".strip()

                    birth_date = ""
                    birth_place = ""

                    # Manuaalinen tagien etsintä (BIRT/CHR -> DATE/PLAC)
                    for child in element.get_child_elements():
                        tag = child.get_tag()
                        if tag in ["BIRT", "CHR"]:
                            for sub_child in child.get_child_elements():
                                if sub_child.get_tag() == "DATE" and not birth_date:
                                    birth_date = sub_child.get_value()
                                if sub_child.get_tag() == "PLAC" and not birth_place:
                                    birth_place = sub_child.get_value()
                            if birth_date and birth_place:
                                break

                    if birth_place and birth_date:
                        birth_year = get_year_from_date(birth_date)
                        if birth_year:
                            data.append({
                                "Nimi": full_name,
                                "Syntymäaika": birth_date,
                                "Vuosi": birth_year,
                                "Paikka": birth_place
                            })
                except Exception:
                    continue
    except Exception as e:
        st.error(f"Virhe tiedoston luvussa: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
    
    return pd.DataFrame(data)

@st.cache_data
def geocode_dataframe(df):
    """Hakee koordinaatit."""
    geolocator = Nominatim(user_agent="family_map_app_v3")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1) 
    
    unique_places = df['Paikka'].unique()
    place_coords = {}
    
    # Progress bar
    my_bar = st.progress(0)
    
    for i, place in enumerate(unique_places):
        my_bar.progress((i + 1) / len(unique_places))
        
        if place not in place_coords:
            query = place
            if "finland" not in place.lower() and "suomi" not in place.lower():
                query = f"{place}, Finland"
            try:
                loc = geocode(query)
                place_coords[place] = (loc.latitude, loc.longitude) if loc else (None, None)
            except:
                place_coords[place] = (None, None)
            
    my_bar.empty()
    
    df['lat'] = df['Paikka'].map(lambda x: place_coords.get(x, (None, None))[0])
    df['lon'] = df['Paikka'].map(lambda x: place_coords.get(x, (None, None))[1])
    
    return df.dropna(subset=['lat', 'lon'])

@st.cache_data
def create_cumulative_data(df, step=5):
    """Luo kertyvän datan animaatiota varten."""
    min_y = int(df['Vuosi'].min())
    max_y = int(df['Vuosi'].max())
    years = range(min_y, max_y + step, step)
    
    cumulative = []
    for y in years:
        mask = df['Vuosi'] <= y
        part = df.loc[mask].copy()
        if not part.empty:
            part['Animaatiovuosi'] = y
            cumulative.append(part)
            
    return pd.concat(cumulative, ignore_index=True) if cumulative else df

# --- 3. PÄÄOHJELMA (MAIN) ---
def main():
    st.title("📍 Sukututkimusdata Kartalla")
    
    st.write("Lataa GEDCOM-tiedosto alla olevasta painikkeesta:")
    
    # TÄMÄ ON SE LATAUSPAINIKE. Se on nyt varmasti näkyvissä.
    uploaded_file = st.file_uploader("Valitse .ged tiedosto", type=['ged'])

    if uploaded_file is not None:
        st.write("---")
        st.info("Tiedosto vastaanotettu. Luetaan dataa...")
        
        bytes_data = uploaded_file.getvalue()
        df = parse_gedcom(bytes_data)
        
        if df.empty:
            st.warning("Tiedostosta ei löytynyt henkilöitä, joilla on sekä syntymäaika että -paikka.")
            st.write("Tarkista, että GEDCOM-tiedostossa on BIRT ja PLAC tagit.")
        else:
            st.success(f"Löydettiin {len(df)} henkilöä!")
            st.dataframe(df.head())

            # Painike koordinaattien hakuun
            if st.button("Hae koordinaatit ja piirrä kartta"):
                with st.spinner("Haetaan sijainteja (tämä vie hetken)..."):
                    df_geo = geocode_dataframe(df)
                
                if df_geo.empty
