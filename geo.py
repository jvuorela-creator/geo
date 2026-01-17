@st.cache_data
def parse_gedcom(file_content):
    """
    Lukee GEDCOM-datan ja palauttaa Pandasin DataFramen.
    Sisältää nyt automaattisen koodauksen korjauksen (UTF-8 / Latin-1).
    """
    
    # --- 1. Koodauksen korjaus ---
    # Yritetään purkaa tavut tekstiksi eri koodauksilla
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
