import os
import sys

# Corrige o path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from infra.database import init_db, save_operation, save_provento, get_operations, get_proventos

def populate_test_db():
    print("Iniciando banco de dados...")
    init_db()

    print("Tentando buscar operações atuais...")
    ops = get_operations()
    if not ops:
        print("Banco vazio. Populando com dados de teste...")
        save_operation("BBSE3", "compra", 100, 30.0)
        save_operation("MXRF11", "compra", 200, 10.0)
        save_provento("BBSE3", 35.0)
        save_provento("MXRF11", 20.0)
        print("Dados inseridos com sucesso!")
    else:
        print(f"Banco já continha {len(ops)} operações. Ignorando seed.")

    # Verificação rápida
    print("\n--- OPERACOES SALVAS ---")
    for o in get_operations():
        print(o)

    print("\n--- PROVENTOS SALVOS ---")
    for p in get_proventos():
        print(p)

if __name__ == "__main__":
    populate_test_db()
