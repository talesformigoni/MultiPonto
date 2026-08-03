import firebase_admin
from firebase_admin import credentials, firestore, auth
import streamlit as st
import os

# Função para inicializar o Firebase apenas uma vez
def inicializar_firebase():
    if not firebase_admin._apps:
        
        # 1. Tenta pegar a chave dos Segredos da Nuvem (Streamlit Cloud)
        if "firebase" in st.secrets:
            cred_dict = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cred_dict)
            
        # 2. Se não achar (significa que está rodando no seu PC), usa a chave local
        else:
            # Pega o caminho do seu arquivo de credenciais local
            cred_path = os.path.join("config", "serviceAccountKey.json")
            cred = credentials.Certificate(cred_path)
            
        firebase_admin.initialize_app(cred)
    
    return firestore.client()

# Instancia o banco de dados
db = inicializar_firebase()