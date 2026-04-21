import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
import os

DB_PATH = os.path.join(os.getcwd(), "database", "users.db")


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# CREAZIONE TABELLE

def create_tables():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('partecipante', 'organizzatore'))
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tipo TEXT CHECK(tipo IN ('giornaliero', 'due_giorni', 'full')) NOT NULL,
            giorno_inizio TEXT,
            giorno_fine TEXT,
            data_acquisto TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artista TEXT NOT NULL UNIQUE,
            giorno TEXT CHECK(giorno IN ('venerdi', 'sabato', 'domenica')) NOT NULL,
            orario_inizio TEXT NOT NULL,
            durata INTEGER NOT NULL,
            descrizione TEXT NOT NULL,
            palco TEXT CHECK(palco IN ('A', 'B', 'C')) NOT NULL,
            genere TEXT NOT NULL,
            pubblicata BOOLEAN NOT NULL DEFAULT 0,
            organizzatore_id INTEGER NOT NULL,
            FOREIGN KEY (organizzatore_id) REFERENCES users(id)
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS immagini (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            performance_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            FOREIGN KEY (performance_id) REFERENCES performance(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()

# UTENTI
def get_users_role(user_id):
    conn = connect_db()
    user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user['role'] if user else None

def get_user_by_email(email):
    conn = connect_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return user

def create_user(email, password, role):
    hashed = generate_password_hash(password)
    conn = connect_db()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", (email, hashed, role))
        conn.commit()
        user_id = cursor.lastrowid
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_id(user_id):
    conn = connect_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user

# BIGLIETTI
def get_tickets_by_user(user_id):
    conn = connect_db()
    rows = conn.execute(
        "SELECT * FROM tickets WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def count_tickets_for_day(giorno):
    conn = connect_db()
    q = """
      SELECT COUNT(*) as cnt FROM tickets
      WHERE
        (tipo = 'giornaliero' AND giorno_inizio = ?)
        OR
        (tipo = 'due_giorni' AND (giorno_inizio = ? OR giorno_fine = ?))
        OR
        (tipo = 'full')
    """
    cur = conn.execute(q, (giorno, giorno, giorno))
    cnt = cur.fetchone()["cnt"]
    conn.close()
    return cnt

def count_tickets_for_tipo(tipo):
    conn = connect_db()
    q = "SELECT COUNT(*) as cnt FROM tickets WHERE tipo = ?"
    cur = conn.execute(q, (tipo,))
    cnt = cur.fetchone()["cnt"]
    conn.close()
    return cnt

def create_ticket(user_id, tipo, giorno_inizio, giorno_fine=None):
    tickets = get_tickets_by_user(user_id)

    if any(t["tipo"] == "full" for t in tickets):
        return (False, "Hai già un full pass.")

    giorni_coperti = set()
    for t in tickets:
        giorni_coperti.add(t["giorno_inizio"])
        if t["giorno_fine"]:
            giorni_coperti.add(t["giorno_fine"])

    if tipo == 'giornaliero':
        if giorno_inizio in giorni_coperti:
            return (False, "Hai già un biglietto per questo giorno.")

        giorni_da_controllare = [giorno_inizio]

    elif tipo == 'due_giorni':
        giorni_nuovi = {giorno_inizio, giorno_fine}

        if giorni_nuovi & giorni_coperti:
            return (False, "Hai già coperto uno di questi giorni.")

        giorni_da_controllare = [giorno_inizio, giorno_fine]

    elif tipo == 'full':
        if tickets:
            return (False, "Hai già acquistato altri biglietti.")

        giorni_da_controllare = ['venerdi', 'sabato', 'domenica']

    MAX_PER_DAY = 200
    for g in giorni_da_controllare:
        if count_tickets_for_day(g) >= MAX_PER_DAY:
            return (False, f"Biglietti esauriti per {g.capitalize()}.")

    conn = connect_db()
    conn.execute(
        "INSERT INTO tickets (user_id, tipo, giorno_inizio, giorno_fine) VALUES (?, ?, ?, ?)",
        (user_id, tipo, giorno_inizio, giorno_fine)
    )
    conn.commit()
    conn.close()

    return (True, "Biglietto acquistato con successo!")

# PERFORMANCE
def crea_performance(artista, giorno, orario_inizio, durata, descrizione, palco, genere, pubblicata, organizzatore_id):
    conn = connect_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO performance (
                artista, giorno, orario_inizio, durata, descrizione,
                palco, genere, pubblicata, organizzatore_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            artista, giorno, orario_inizio, durata, descrizione,
            palco, genere, pubblicata, organizzatore_id
        ))
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_bozze_by_organizzatore(user_id):
    conn = connect_db()
    bozze = conn.execute("""
        SELECT * FROM performance 
        WHERE organizzatore_id = ? AND pubblicata = 0
    """, (user_id,)).fetchall()

    result = []
    for bozza in bozze:
        bozza_dict = dict(bozza)
        immagini = conn.execute("""
            SELECT * FROM immagini 
            WHERE performance_id = ?
        """, (bozza['id'],)).fetchall()
        bozza_dict['immagini'] = [dict(img) for img in immagini]
        result.append(bozza_dict)

    conn.close()
    return result


def get_performance_by_id_and_organizzatore(perf_id, user_id):
    conn = connect_db()
    row = conn.execute(
        "SELECT * FROM performance WHERE id = ? AND organizzatore_id = ? AND pubblicata = 0",
        (perf_id, user_id)
    ).fetchone()
    conn.close()
    return row

def get_eventi_pubblici():
    conn = connect_db()
    eventi = conn.execute("""
        SELECT * FROM performance 
        WHERE pubblicata = 1 
        ORDER BY giorno, orario_inizio
    """).fetchall()

    result = []
    for evento in eventi:
        evento_dict = dict(evento)
        immagini = conn.execute("""
            SELECT * FROM immagini 
            WHERE performance_id = ?
        """, (evento['id'],)).fetchall()
        evento_dict['immagini'] = [dict(img) for img in immagini]
        result.append(evento_dict)

    conn.close()
    return result

def get_eventi_filtrati(giorno=None, palco=None, genere=None):
    conn = connect_db()

    query = """
        SELECT performance.*, immagini.file_path AS immagine
        FROM performance
        LEFT JOIN immagini 
            ON immagini.id = (
                SELECT id FROM immagini 
                WHERE performance_id = performance.id 
                ORDER BY id ASC 
                LIMIT 1
            )
        WHERE pubblicata = 1
    """

    params = []

    if giorno:
        query += " AND giorno = ?"
        params.append(giorno)

    if palco:
        query += " AND palco = ?"
        params.append(palco)

    if genere:
        query += " AND genere = ?"
        params.append(genere)

    eventi = conn.execute(query, params).fetchall()
    conn.close()
    return eventi

def artista_gia_usato(nome_artista, *, exclude_id=None):
    conn = connect_db()
    query = "SELECT 1 FROM performance WHERE artista = ?"
    params = [nome_artista]
    if exclude_id:
        query += " AND id != ?"
        params.append(exclude_id)
    result = conn.execute(query, params).fetchone()
    conn.close()
    return result is not None

def verifica_conflitto_orario(orario_iso, durata, palco,*, exclude_id=None):
    """
    Verifica se esiste una performance sovrapposta nello stesso giorno/palco.
    - `orario_iso`: stringa "YYYY-MM-DD HH:MM:SS"
    - `durata`: intero (minuti)
    - `palco`: stringa (es. "A")
    - `exclude_id`: opzionale, per ignorare l'id corrente
    """
    conn = connect_db()

    # Calcola l'intervallo di tempo dell'evento nuovo
    start_dt = datetime.strptime(orario_iso, "%Y-%m-%d %H:%M:%S")
    end_dt = start_dt + timedelta(minutes=durata)
    start_iso = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_iso = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    query = """
        SELECT 1 FROM performance
        WHERE pubblicata = 1
        AND palco = ?
        AND (
                (? < datetime(orario_inizio, '+' || durata || ' minutes'))
            AND (? > orario_inizio)
        )
    """

    params = [palco, start_iso, end_iso]

    if exclude_id:
        query += " AND id != ?"
        params.append(exclude_id)

    result = conn.execute(query, params).fetchone()
    conn.close()

    return result is not None  # True se c'è un conflitto

def get_performance_by_id(perf_id):
    conn = connect_db()
    row = conn.execute("SELECT * FROM performance WHERE id = ?", (perf_id,)).fetchone()
    conn.close()
    return row

# Ottiene i generi unici per il filtro
def get_generi_unici():
    conn = connect_db()
    rows = conn.execute(
        "SELECT DISTINCT genere FROM performance WHERE pubblicata = 1 ORDER BY genere"
    ).fetchall()
    conn.close()

    return [r["genere"] for r in rows]

def delete_performance(perf_id):
    conn = connect_db()
    conn.execute("DELETE FROM performance WHERE id = ?", (perf_id,))
    conn.execute("DELETE FROM immagini WHERE performance_id = ?", (perf_id,))
    conn.commit()
    conn.close()

# IMMAGINI
def crea_immagine(performance_id, file_path):
    conn = connect_db()
    conn.execute(
        "INSERT INTO immagini (performance_id, file_path) VALUES (?, ?)",
        (performance_id, file_path)
    )
    conn.commit()
    conn.close()

def get_immagini_by_performance(perf_id):
    conn = connect_db()
    imgs = conn.execute(
        "SELECT * FROM immagini WHERE performance_id = ?", (perf_id,)
    ).fetchall()
    conn.close()
    return imgs

def get_immagine_by_id(img_id):
    conn = connect_db()
    img = conn.execute("SELECT * FROM immagini WHERE id = ?", (img_id,)).fetchone()
    conn.close()
    return img

def delete_immagine(img_id):
    conn = connect_db()
    conn.execute("DELETE FROM immagini WHERE id = ?", (img_id,))
    conn.commit()
    conn.close()




