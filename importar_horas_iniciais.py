import firebase_admin
from firebase_admin import credentials, firestore
import os

print("⚡ Conectando ao Firebase...")
cred_path = os.path.join("config", "serviceAccountKey.json")

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Dados oficiais mapeados pelo UID exato
residentes_dados = {
    "iRi3PtLESmQSs90cV2e40lLkOmW2": {
        "nome_completo": "Benedito Tales Santos Sousa Formigoni",
    },
    "3LLmvIsF5hXHq6Pn9RNwxVMTqpw2": {
        "nome_completo": "Marcia Sales Belfort",
    },
    "hMr49kqoVOdvjodwk5ZebAar94Y2": {
        "nome_completo": "Pamela Daniele De Sousa",
    },
    "HSa6kflLCggnFc0vlv5oTtEIIrL2": {
        "nome_completo": "Fabiana Martins Vieira",
    },
    "se6oDmXBN3hM0fuvMS9NniU0Pa62": {
        "nome_completo": "Andrea Raissa Bonfim Medeiros",
    },
    "qLLuY5m7o8XyEKYOXxtYKJIx2Nk2": {
        "nome_completo": "Maria Neves Lopes Menezes",
    },
    "iTnIQu3uPTXjm1jvIA6ETtPqGo52": {
        "nome_completo": "Paulo Fernandes Dos Santos",
    },
    "F36rrAhX6BR5Bc7oarARMp70ktp2": {
        "nome_completo": "Betânia Pereira Pardinho",
    },
    "EUNfnTJsa2ZGbGqSrWZjdvy3pwu2": {
        "nome_completo": "Daniely Kunrath",
    }
}

# Dias alvo para receberem as 9h diárias
dias_alvo = [
    "2026-03-09",
    "2026-03-10",
    "2026-03-11",
    "2026-03-12",
    "2026-03-13"
]

mes_ref = "03/2026"
categoria_ponto = "Prática"
horas_por_dia = 9.0

# Horário padrão que fecha exatas 9 horas (5h de manhã + 4h à tarde)
horarios_descritos = ["07:00 às 12:00", "13:30 às 17:30"]
justificativa = "Semana de Acolhimento / Integração (Importado em Lote)"

print("Iniciando injeção de pontos (45h totais)...")

for uid, dados in residentes_dados.items():
    nome = dados["nome_completo"]
    
    # Regra de Exceção
    if nome == "Maria Neves Lopes Menezes":
        print(f"⏭️ Pulando residente: {nome} (Exceção solicitada)")
        continue
        
    print(f"⏳ Lançando 45 horas para: {nome}...")
    
    # Lançando os 5 dias para o residente atual
    for data_str in dias_alvo:
        # ID do documento seguindo a mesma arquitetura do seu app.py
        doc_id = f"{uid}_{data_str}_{categoria_ponto}"
        
        dados_ponto = {
            "uid_residente": uid,
            "data_registro": data_str,
            "mes_referencia": mes_ref,
            "categoria": categoria_ponto,
            "horas_computadas": horas_por_dia,
            "horarios_descritos": horarios_descritos,
            "justificativa": justificativa,
            "ultima_edicao": firestore.SERVER_TIMESTAMP
        }
        
        # Grava no banco de dados
        db.collection("pontos").document(doc_id).set(dados_ponto)
        
    print(f"✅ 45h (5 dias) creditadas com sucesso para {nome}!\n")

print("🚀 SUCESSO TOTAL! Todos os pontos iniciais foram lançados.")