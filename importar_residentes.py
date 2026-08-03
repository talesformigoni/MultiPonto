import firebase_admin
from firebase_admin import credentials, firestore
import os

print("⚡ Conectando ao Firebase...")
cred_path = os.path.join("config", "serviceAccountKey.json")

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Dados oficiais mapeados pelo UID exato enviado
residentes_dados = {
    "iRi3PtLESmQSs90cV2e40lLkOmW2": {
        "nome_completo": "Benedito Tales Santos Sousa Formigoni",
        "profissao": "Nutrição",
        "email": "tales.nutri@gmail.com",
        "whatsapp": "(41) 98435-6395",
        "data_nascimento": "10/01/1997",
        "cpf": "040.676.563-43",
        "numero_conselho": "CRN 19271"
    },
    "3LLmvIsF5hXHq6Pn9RNwxVMTqpw2": {
        "nome_completo": "Marcia Sales Belfort",
        "profissao": "Assistente Social",
        "email": "marciabelfortmoraes@gmail.com",
        "whatsapp": "69 99992-5428",
        "data_nascimento": "04/05/1984",
        "cpf": "710.883.342-53",
        "numero_conselho": "CRESS 3131"
    },
    "hMr49kqoVOdvjodwk5ZebAar94Y2": {
        "nome_completo": "Pamela Daniele De Sousa",
        "profissao": "Psicologia",
        "email": "pameladanielesousa@gmail.com",
        "whatsapp": "(69) 9 9371-6203",
        "data_nascimento": "09/10/1995",
        "cpf": "029.741.172-10",
        "numero_conselho": "CRP 24/05164"
    },
    "HSa6kflLCggnFc0vlv5oTtEIIrL2": {
        "nome_completo": "Fabiana Martins Vieira",
        "profissao": "Odontologia",
        "email": "bianamrs@hotmail.com",
        "whatsapp": "69984898821",
        "data_nascimento": "26/10/1990",
        "cpf": "009.575.652-32",
        "numero_conselho": "CRO 4776"
    },
    "se6oDmXBN3hM0fuvMS9NniU0Pa62": {
        "nome_completo": "Andrea Raissa Bonfim Medeiros",
        "profissao": "Odontologia",
        "email": "drandreabonfim@gmail.com",
        "whatsapp": "69 992241246",
        "data_nascimento": "05/02/2002",
        "cpf": "050.521.442-37",
        "numero_conselho": "CRO 5462"
    },
    "qLLuY5m7o8XyEKYOXxtYKJIx2Nk2": {
        "nome_completo": "Maria Neves Lopes Menezes",
        "profissao": "Fisioterapia",
        "email": "marinevlop@gmail.com",
        "whatsapp": "(69) 99219-3931",
        "data_nascimento": "05/08/1974",
        "cpf": "498.896.212-15",
        "numero_conselho": "CREFITO 396823-F"
    },
    "iTnIQu3uPTXjm1jvIA6ETtPqGo52": {
        "nome_completo": "Paulo Fernandes Dos Santos",
        "profissao": "Farmácia",
        "email": "paulinhoburitis1@gmail.com",
        "whatsapp": "(69) 9 9265 - 8139",
        "data_nascimento": "11/07/1986",
        "cpf": "340.863.528-50",
        "numero_conselho": "CRF 4247"
    },
    "F36rrAhX6BR5Bc7oarARMp70ktp2": {
        "nome_completo": "Betânia Pereira Pardinho",
        "profissao": "Enfermagem",
        "email": "betaniaa.pardinho@gmail.com",
        "whatsapp": "69 99244-2674",
        "data_nascimento": "18/05/2000",
        "cpf": "040.013.772-09",
        "numero_conselho": "COREN 765941"
    },
    "EUNfnTJsa2ZGbGqSrWZjdvy3pwu2": {
        "nome_completo": "Daniely Kunrath",
        "profissao": "Enfermagem",
        "email": "kunrath_dani@hotmail.com",
        "whatsapp": "(69)993151234",
        "data_nascimento": "26/06/1999",
        "cpf": "041.379.362-18",
        "numero_conselho": "COREN 911144"
    }
}

print("Iniciando injeção de dados estruturados por UID...")
for uid, dados in residentes_dados.items():
    # Mantém os campos dinâmicos necessários para o ecossistema do app
    dados["lotacao"] = "A definir (Atualize no painel)"
    dados["preceptor"] = "A definir (Atualize no painel)"
    dados["perfil"] = "Residente"
    dados["primeiro_login"] = True
    
    # Grava usando o UID real como a chave primária da coleção
    db.collection("residentes").document(uid).set(dados)
    print(f"✅ Ficha sincronizada pelo UID [{uid}]: {dados['nome_completo']}")

print("\n🚀 SUCESSO TOTAL! Banco de dados atualizado no padrão ouro.")