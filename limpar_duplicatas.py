import firebase_admin
from firebase_admin import credentials, firestore
import os

print("⚡ Conectando ao Firebase...")
cred_path = os.path.join("config", "serviceAccountKey.json")

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

print("🔍 Escaneando o banco de dados em busca de pontos...")
pontos_ref = db.collection("pontos").stream()

# Dicionário para rastrear os registros originais que vamos manter
registros_vistos = {}
docs_para_excluir = []

for p in pontos_ref:
    dados = p.to_dict()
    doc_id = p.id
    
    uid = dados.get("uid_residente", "")
    data_reg = dados.get("data_registro", "")
    cat = dados.get("categoria", "")
    horas = dados.get("horas_computadas", 0)
    
    # Pula documentos que por acaso estejam quebrados ou vazios
    if not uid or not data_reg or not cat:
        continue 
        
    # Criando a "impressão digital" do ponto
    # Se for do mesmo residente, mesmo dia, mesma categoria e mesmas horas = DUPLICATA
    chave_unica = (uid, data_reg, cat, horas)
    
    if chave_unica in registros_vistos:
        # Já vimos esse registro! Adiciona na lista de execução
        docs_para_excluir.append(doc_id)
    else:
        # É a primeira vez que vemos esse registro, salva como o "original"
        registros_vistos[chave_unica] = doc_id

print(f"🚨 Encontradas {len(docs_para_excluir)} duplicatas!")

# Executando a limpeza
if len(docs_para_excluir) > 0:
    print("🗑️ Iniciando a exclusão dos clones...")
    
    # Usando Batch para excluir tudo de forma mais rápida e otimizada
    lote = db.batch()
    contador = 0
    
    for doc_id in docs_para_excluir:
        doc_ref = db.collection("pontos").document(doc_id)
        lote.delete(doc_ref)
        contador += 1
        
        # O Firebase tem um limite de 500 operações por lote
        if contador == 500:
            lote.commit()
            print("⏳ Commit de 500 exclusões realizado...")
            lote = db.batch()
            contador = 0
            
    # Commita qualquer resto que sobrou (se for menor que 500)
    if contador > 0:
        lote.commit()
        
    print(f"✅ Limpeza concluída! {len(docs_para_excluir)} registros fantasmas foram apagados.")
else:
    print("✨ Tudo limpo! Nenhuma duplicata foi encontrada no sistema.")