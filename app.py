from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import date, time, datetime
import db
import os

app = Flask(__name__)
app.secret_key = "ApplicazioniWebEsameSecretKey"

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Inizializzazione del DB
with app.app_context():
    db.create_tables()

# Manda ticket esistente ai template
@app.context_processor
def inject_tickets():
    tickets = []
    if "user_id" in session:
        user_id = session["user_id"]
        tickets = db.get_tickets_by_user(user_id)
    return dict(tickets=tickets)

# INDEX
@app.route("/")
def index():
     giorno = request.args.get("giorno")
     palco = request.args.get("palco")
     genere = request.args.get("genere")

     eventi = db.get_eventi_filtrati(giorno, palco, genere)
     generi = db.get_generi_unici()

     open_modal = session.pop("open_modal", None)  # Toglie dalla sessione
     return render_template("home.html", open_modal=open_modal, eventi_pubblici=eventi, generi=generi)

# INFO
@app.route("/info")
def info():
    return render_template("info.html")

# Carica le informazioni dell'utente nella sessione
def login_user(user):
    session["user_id"] = user["id"]
    session["email"] = user["email"]
    session["ruolo"] = user["role"]


# REGISTRAZIONE
@app.route("/register", methods=["POST"])
def register():
    email = request.form["email"]
    password = request.form["password"]
    conferma = request.form["conferma_password"]
    ruolo = request.form["ruolo"]

    if password != conferma:
        flash("Le password non coincidono.", "danger")
        session["open_modal"] = "registerModalPartecipante" if ruolo == "partecipante" else "authModal"
        return redirect(request.referrer or url_for("index"))

    if db.get_user_by_email(email):
        flash("Email già registrata.", "warning")
        session["open_modal"] = "registerModalPartecipante" if ruolo == "partecipante" else "authModal"
        return redirect(request.referrer or url_for("index"))

    # Crea l'utente nel DB
    user_id = db.create_user(email, password, ruolo)

    # Autologin subito dopo la registrazione
    user= db.get_user_by_id(user_id)
    login_user(user)

    flash("Registrazione avvenuta con successo!", "success")

    if ruolo == "partecipante":
        return redirect(url_for("participant_tickets"))
    elif ruolo == "organizzatore":
        return redirect(url_for("dashboard_organizzatore")) 


# LOGIN
@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]

    user = db.get_user_by_email(email)
    if user and check_password_hash(user["password"], password):
        login_user(user) 
        flash("Accesso effettuato con successo!", "success")

        # Redirect in base al ruolo
        if user["role"] == "partecipante":
            return redirect(url_for("participant_tickets"))
        elif user["role"] == "organizzatore":
            return redirect(url_for("dashboard_organizzatore"))
    else:
        flash("Email o password errati.", "danger")
        session["open_modal"] = "loginModal" 
        return redirect(url_for("index"))

# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    flash("Sei stato disconnesso.", "info")
    return redirect(url_for("index"))

# Decoratore per proteggere le route a partecipanti
def login_required(role=None):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash("Devi fare login per accedere.", "warning")
                return redirect(url_for("index"))
            if role and session.get("ruolo") != role:
                flash("Non hai i permessi per accedere a questa pagina.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated
    return wrapper

# Decoratore per proteggere le route a organizzatori
def login_required_organizer(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session or session.get("ruolo") != "organizzatore":
            flash("Devi essere un organizzatore per accedere a questa pagina.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

# DASHBOARD PARTECIPANTI
@app.route("/partecipante", methods=["GET", "POST"])
@login_required(role="partecipante")
def participant_tickets():
    user_id = session["user_id"]
    tickets = db.get_tickets_by_user(user_id)
    
    giorni_coperti = set()
    for t in tickets:
        giorni_coperti.add(t["giorno_inizio"])
        if t["giorno_fine"]:
            giorni_coperti.add(t["giorno_fine"])

    #Logica per disabilitare opzioni
    tutti_giorni = {"venerdi", "sabato", "domenica"}
    giorni_disponibili = tutti_giorni - giorni_coperti

    has_full = any(t["tipo"] == "full" for t in tickets)

    disable_full = len(tickets) > 0
    disable_giornaliero = has_full or len(giorni_disponibili) == 0

    disable_due_giorni = True
    if "venerdi" in giorni_disponibili and "sabato" in giorni_disponibili:
        disable_due_giorni = False
    if "sabato" in giorni_disponibili and "domenica" in giorni_disponibili:
        disable_due_giorni = False

    giorno = request.args.get("giorno")
    palco = request.args.get("palco")
    genere = request.args.get("genere")

    eventi = db.get_eventi_filtrati(giorno, palco, genere)
    generi = db.get_generi_unici()

    # Se il form viene inviato (POST), cerchiamo di creare il ticket
    if request.method == "POST":
        tipo = request.form["tipo"]
        giorno_inizio = request.form.get("giorno_inizio")

        # Blocco domenica
        if tipo == "due_giorni" and giorno_inizio == "domenica":
            flash("Non puoi iniziare un pass da 2 giorni di domenica.", "danger")
            return redirect(url_for("participant_tickets"))

        if tipo == "giornaliero" and giorno_inizio in giorni_coperti:
            flash("Hai già un biglietto per questo giorno.", "danger")
            return redirect(url_for("participant_tickets"))

        if tipo == "due_giorni":
            if giorno_inizio == "venerdi" and "venerdi" in giorni_coperti:
                flash("Hai già coperto uno di questi giorni.", "danger")
                return redirect(url_for("participant_tickets"))
            if giorno_inizio == "sabato" and "sabato" in giorni_coperti:
                flash("Hai già coperto uno di questi giorni.", "danger")
                return redirect(url_for("participant_tickets"))

        if tipo == "full" and tickets:
            flash("Hai già acquistato altri biglietti.", "danger")
            return redirect(url_for("participant_tickets"))

        # Se two-day, calcolo giorno_fine
        giorno_fine = None
        if tipo == "due_giorni":
            if giorno_inizio == "venerdi":
                giorno_fine = "sabato"
            elif giorno_inizio == "sabato":
                giorno_fine = "domenica"
        elif tipo == "full":
            giorno_inizio = "venerdi"
            giorno_fine = "domenica"

        success, msg = db.create_ticket(user_id, tipo, giorno_inizio, giorno_fine)
        flash(msg, "success" if success else "danger")

        return redirect(url_for("participant_tickets"))

    # Contiamo quanti biglietti per ciascun giorno
    posti_venerdi = db.count_tickets_for_day("venerdi")
    posti_sabato  = db.count_tickets_for_day("sabato")
    posti_domenica= db.count_tickets_for_day("domenica")

    return render_template(
        "partecipanti.html",
        tickets=tickets,
        giorni_coperti=giorni_coperti,
        disable_full=disable_full,
        disable_giornaliero=disable_giornaliero,
        disable_due_giorni=disable_due_giorni,
        posti={
            "venerdi": posti_venerdi,
            "sabato": posti_sabato,
            "domenica": posti_domenica
        },
        eventi_pubblici=eventi,
        generi=generi
    )

# DASHBOARD ORGANIZZATORE
@app.route("/organizzatore")
@login_required(role="organizzatore")
def dashboard_organizzatore():
    user_id = session["user_id"]
    # Bozze e eventi pubblici
    bozze = db.get_bozze_by_organizzatore(user_id)
    
    giorno = request.args.get("giorno")
    palco = request.args.get("palco")
    genere = request.args.get("genere")

    eventi = db.get_eventi_filtrati(giorno, palco, genere)
    generi = db.get_generi_unici()

    # Contiamo quanti biglietti per ciascun tipo
    tickets_giornaliero = db.count_tickets_for_tipo("giornaliero")
    tickets_due_giorni = db.count_tickets_for_tipo("due_giorni")
    tickets_full = db.count_tickets_for_tipo("full")
    # Contiamo quanti biglietti per ciascun giorno
    posti_venerdi = db.count_tickets_for_day("venerdi")
    posti_sabato  = db.count_tickets_for_day("sabato")
    posti_domenica= db.count_tickets_for_day("domenica")
    

    # Se arriva edit_id, prepariamo la bozza per il modale
    edit_id = request.args.get("edit_id", type=int)
    bozza_to_edit = None

    if edit_id:
        # Recupera la bozza dal DB
        row = db.get_performance_by_id_and_organizzatore(edit_id, user_id)
        if row:
            bozza_to_edit = dict(row)
            bozza_to_edit["immagini"] = db.get_immagini_by_performance(edit_id)
        else:
            flash("Bozza non trovata o non hai i permessi per modificarla.", "danger")
            return redirect(url_for("dashboard_organizzatore"))

    return render_template(
        "organizzatori.html",
        existing_ticket=None,  # Non serve per l'organizzatore
        tickets={
            "giornaliero": tickets_giornaliero,
            "due_giorni": tickets_due_giorni,
            "full": tickets_full
        },
        posti={
            "venerdi": posti_venerdi,
            "sabato": posti_sabato,
            "domenica": posti_domenica
        },
        bozze=bozze,
        eventi_pubblici=eventi,
        generi=generi,
        bozza_to_edit=bozza_to_edit
    )


# Funzione per verificare le estensioni dei file caricati
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# CREAZIONE PERFORMANCE
@app.route("/organizzatore/crea", methods=["POST"])
@login_required(role="organizzatore")
def crea_evento():
    artista = request.form["titolo"]

    if db.artista_gia_usato(artista):
        flash("Errore: artista già registrato in un'altra performance.", "danger")
        return redirect(url_for("dashboard_organizzatore"))

    descrizione = request.form["descrizione"]
    giorno = request.form["giorno"]
    orario = request.form["orario"]
    palco = request.form["palco"]

    try:
        durata = int(request.form["durata"])
    except ValueError:
        flash("Durata non valida", "danger")
        return redirect(url_for("dashboard_organizzatore"))
    
    genere = request.form["genere"]
    pubblicata = 0 if "bozza" in request.form else 1
    organizzatore_id = session["user_id"]

    # Data “reale” del festival:
    data_iso   = GIORNI_FESTIVAL[giorno]
    # Ora armata di data:
    orario_iso = f"{data_iso} {orario}:00"

    # Controllo conflitti di orario
    if db.verifica_conflitto_orario(orario_iso, durata, palco):
        flash("Errore: conflitto di orario o palco già prenotato.", "danger")
        return redirect(url_for("dashboard_organizzatore"))

    # 1) Crea la performance
    perf_id = db.crea_performance(
        artista, giorno, orario_iso, durata, descrizione,
        palco, genere, pubblicata, organizzatore_id
    )

    if not perf_id:
        flash("Errore: artista già registrato o dati non validi.", "danger")
        return redirect(url_for("dashboard_organizzatore"))

    # 2) Gestione upload immagini
    files = request.files.getlist('immagini')
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            # Salva la reference nel DB
            db.crea_immagine(performance_id=perf_id, file_path=f"uploads/{filename}")

    flash("Performance creata con successo!", "success")
    return redirect(url_for("dashboard_organizzatore"))

# Mappa dei giorni del festival
GIORNI_FESTIVAL = {
    "venerdi":  "2025-06-13",
    "sabato":   "2025-06-14",
    "domenica": "2025-06-15",
}

# MODIFICA BOZZA
@app.route("/organizzatore/modifica/<int:id>", methods=["POST"])
@login_required(role="organizzatore")
def modifica_evento(id):
    # 1) Preleva i dati dal form (stessi name del crea)
    artista = request.form["titolo"]

    if db.artista_gia_usato(artista, exclude_id=id):
        flash("Errore: artista già registrato in un'altra performance.", "danger")
        return redirect(url_for("dashboard_organizzatore"))

    descrizione = request.form["descrizione"]
    giorno = request.form["giorno"]
    orario = request.form["orario"]
    palco = request.form["palco"]

    try:
        durata = int(request.form["durata"])
    except ValueError:
        flash("Durata non valida", "danger")
        return redirect(url_for("dashboard_organizzatore"))
    
    genere      = request.form["genere"]
    pubblicata  = 1 if "bozza" not in request.form else 0

    # Data “reale” del festival:
    data_iso   = GIORNI_FESTIVAL[giorno]
    # Ora armata di data:
    orario_iso = f"{data_iso} {orario}:00"

    # Controllo conflitti di orario
    if db.verifica_conflitto_orario(orario_iso, durata, palco, exclude_id=id):
        flash("Errore: conflitto di orario o palco già prenotato.", "danger")
        return redirect(url_for("dashboard_organizzatore"))

    # 2) Aggiorna la bozza/performance
    conn = db.connect_db()
    conn.execute("""
        UPDATE performance
        SET artista        = ?,
            descrizione    = ?,
            giorno         = ?,
            orario_inizio  = ?,
            palco          = ?,
            durata         = ?,
            genere         = ?,
            pubblicata     = ?
        WHERE id = ? 
          AND organizzatore_id = ?
    """, (
        artista,
        descrizione,
        giorno,
        orario_iso,
        palco,
        durata,
        genere,
        pubblicata,
        id,
        session["user_id"]
    ))
    conn.commit()
    conn.close()

    # 3) Gestione cancellazione immagini esistenti
    for key in request.form:
        if key.startswith("delete_image_"):
            img_id = int(key.split("_")[-1])
            img = db.get_immagine_by_id(img_id)
            if img and img['performance_id'] == id:
                # elimina dal DB
                db.delete_immagine(img_id)
                # elimina file fisico
                try:
                    os.remove(os.path.join(app.static_folder, img['file_path']))
                except OSError:
                    # se non esiste o non permesso, prosegui
                    pass

    # 4) Gestione nuovi upload
    files = request.files.getlist('immagini')
    for file in files:
        if file and allowed_file(file.filename):
            filename  = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            # crea record nel DB
            db.crea_immagine(performance_id=id, file_path=f"uploads/{filename}")

    flash("Bozza aggiornata con successo!", "success")
    return redirect(url_for("dashboard_organizzatore"))

# ELIMINA BOZZA
@app.route("/organizzatore/elimina/<int:id>", methods=["POST"])
@login_required(role="organizzatore")
def elimina_bozza(id):
    bozza = db.get_performance_by_id(id)
    if not bozza or bozza['organizzatore_id'] != session["user_id"] or bozza['pubblicata'] == 1:
        flash("Operazione non consentita.", "danger")
        return redirect(url_for("dashboard_organizzatore"))

    # Elimina immagini collegate
    immagini = db.get_immagini_by_performance(id)
    for img in immagini:
        try:
            os.remove(os.path.join(app.static_folder, img['file_path']))
        except OSError:
            pass
        db.delete_immagine(img['id'])

    # Elimina la bozza
    db.delete_performance(id)

    flash("Bozza eliminata con successo.", "success")
    return redirect(url_for("dashboard_organizzatore"))


# Dettaglio evento
@app.route("/evento/<int:id>")
def dettaglio_evento(id):
    evento = db.get_performance_by_id(id)
    if not evento:
        flash("Evento non trovato.", "danger")
        return redirect(url_for("index"))
    evento = dict(evento)
    evento["immagini"] = db.get_immagini_by_performance(id)
    return render_template("evento.html", evento=evento)



