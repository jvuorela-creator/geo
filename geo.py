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

st.title("📍 Sukututkimusdata Kartalla (Debug-tila)")

# --- APUFUNKTIOT ---

def get_year_from_date(date_str):
    if not date_str:
        return None
    # Etsitään 4 numeroa (esim. 1850)
    match = re.search(r'\d{4}', str(date_str))
    return int(match.group(0)) if match else None

@st.cache_data
def parse_gedcom(file_content):
    """
    Kestävä jäsennys, joka etsii BIRT/PLAC tageja manuaalisesti.
    """
    
    # 1. Koodauksen korjaus (UTF-8 / Latin-1 / ANSI)
    decoded_text = ""
    try:
        decoded_text = file_content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            decoded_text = file_content.decode('latin-1')
        except Exception:
            decoded_text = file_content.decode('utf-8', errors='ignore')

    # 2. Tyhjien rivien siivous
    lines = decoded_text.splitlines()
    clean_lines = [line for line in lines if line.strip()]
    cleaned_text = "\n".join(clean_lines)

    # 3. Väliaikainen tiedosto
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ged", mode='w', encoding='utf-8') as tmp_file:
            tmp_file.write(cleaned_text)
            tmp_path = tmp_file.name

        # 4. Jäsennys strict=False
        gedcom_parser = Parser()
        gedcom_parser.parse_file(tmp_path, strict=False)
        
        root_child_elements = gedcom_parser.get_root_child_elements()
        data = []

        # --- MANUAALINEN JÄSENNYS ---
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

                    # Käydään läpi henkilön kaikki alitagit (lapset) manuaalisesti
                    # Etsitään BIRT (syntymä) tai CHR (kaste)
                    for child in element.get_child_elements():
                        tag = child.get_tag()
                        
                        if tag == "BIRT" or tag == "CHR":
                            # Jos löytyi syntymä- tai kastetapahtuma, katsotaan sen sisälle
                            for sub_child in child.get_child_elements():
                                sub_tag = sub_child.get_tag()
                                sub_val = sub_child.get_value()
                                
                                if sub_tag == "DATE" and not birth_date:
                                    birth_date = sub_val
                                if sub_tag == "PLAC" and not birth_place:
                                    birth_place = sub_val
                            
                            # Jos molemmat löytyi, lopetetaan etsintä tämän hlön osalta
                            if birth_date and birth_place:
                                break

                    # Tallennetaan jos tiedot löytyi
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
                    
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    
    return pd.DataFrame(data)

@st.cache_data
def geocode_dataframe(df):
    geolocator = Nominatim(user_agent="streamlit_family_map_final_fix")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1) 
    
    unique_places = df['Paikka'].unique()
    place_coords = {}
    
    progress_bar = st.progress(0)
    status_text
