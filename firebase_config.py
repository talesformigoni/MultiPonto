import firebase_admin
from firebase_admin import credentials, firestore, auth
import streamlit as st
import os
import json

def inicializar_firebase():
    if not firebase_admin._apps:
        # 1. Tenta carregar o JSON completo direto dos Segredos da Nuvem
        if "FIREBASE_JSON" in st.secrets:
            cred_info = json.loads(st.secrets["FIREBASE_JSON"])
            cred = credentials.Certificate(cred_info)
        elif "firebase" in st.secrets:
            # Compatibilidade com o formato antigo
            cred_dict = dict(st.secrets["firebase"])
            if "private_key" in cred_dict:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
        else:
            # 2. Se estiver rodando no seu PC, usa o arquivo local
            cred_path = os.path.join("config", "serviceAccountKey.json")
            cred = credentials.Certificate(cred_path)
            
        firebase_admin.initialize_app(cred)
    
    return firestore.client()

db = inicializar_firebase()
