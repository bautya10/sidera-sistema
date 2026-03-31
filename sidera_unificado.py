"""
SISTEMA SIDERA UNIFICADO
Control de Conciliaciones + Extractor de Comprobantes
Versión Streamlit Cloud - Marzo 2026
"""

import streamlit as st
import sqlite3
import zipfile
import io
import os
import time
import json
import re
import base64
import difflib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
import anthropic

# =============================================================================
# CONFIGURACIÓN INICIAL
# =============================================================================

st.set_page_config(
    page_title="Sistema Sidera",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cargar .env si existe (para desarrollo local)
def _cargar_env_local():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_cargar_env_local()

# Constantes
DB_NAME = "sidera_datos.db"
CLIENTES_CONTROL = ['Giardino', 'Fimex', 'Alcaide', 'Red Bird', 'Parra', 'Moreira', 'Giampaoli', 'CC General', 'Ajustes Manuales']
CLIENTES_EXTRACTOR = ["Celso", "Canella", "Vertice", "3D Land", "Moreira", "Giampaoli"]

# =============================================================================
# FUNCIONES DE BASE DE DATOS
# =============================================================================

def init_db():
    """Inicializa la base de datos con las tablas necesarias"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Tabla de transacciones
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                solicitante TEXT NOT NULL,
                sub_cliente TEXT,
                titular TEXT NOT NULL,
                monto REAL NOT NULL,
                estado TEXT NOT NULL,
                fecha_pedido TEXT NOT NULL,
                nivel_alerta TEXT,
                datos_extraidos TEXT,
                id_operacion TEXT
            )
        ''')
        
        # Tabla de saldos diarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saldos_diarios (
                fecha TEXT PRIMARY KEY,
                nexo_ingresos REAL DEFAULT 0,
                nexo_egresos REAL DEFAULT 0
            )
        ''')
        
        conn.commit()

def get_db_connection():
    """Retorna conexión a la base de datos"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# FUNCIONES DE LIMPIEZA Y PROCESAMIENTO
# =============================================================================

def limpiar_nombre(nombre: str) -> str:
    """Limpia el nombre removiendo comas"""
    if not nombre:
        return ""
    return nombre.replace(",", "").strip()

def limpiar_monto(monto_str: str) -> float:
    """Limpia el monto y lo convierte a float"""
    if not monto_str:
        return 0.0
    
    monto = re.sub(r'[$USD€ARS\s]', '', str(monto_str))
    
    if re.search(r'[.,]\d{2}$', monto):
        if '.' in monto and ',' in monto:
            if monto.rindex('.') > monto.rindex(','):
                monto = monto.replace(',', '')
                monto = monto.replace('.', ',')
            else:
                monto = monto.replace('.', '')
        elif '.' in monto:
            monto = monto.replace('.', ',')
    else:
        monto = monto.replace('.', '').replace(',', '')
    
    monto = monto.replace(',', '.')
    
    try:
        return float(monto)
    except:
        return 0.0

def pdf_a_imagen_png(pdf_bytes: bytes) -> bytes:
    """Convierte PDF a imagen PNG"""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pagina = doc[0]
    mat = fitz.Matrix(2.0, 2.0)
    pix = pagina.get_pixmap(matrix=mat)
    return pix.tobytes("png")

def extraer_datos_con_vision_api(archivo_contenido: bytes, nombre_archivo: str, 
                                 tipo_archivo: str) -> Dict[str, str]:
    """Extrae datos del comprobante usando Claude API"""
    
    api_key = st.secrets.get("ANTHROPIC_API_KEY", None) if hasattr(st, "secrets") else None
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        st.error("⚠️ API Key no configurada.")
        return {"emisor": "", "monto": "0", "destinatario": "", "id_operacion": "", "fecha": "", "horario": ""}
    
    try:
        client = anthropic.Anthropic(api_key=api_key)

        if tipo_archivo == 'application/pdf' or nombre_archivo.lower().endswith('.pdf'):
            try:
                archivo_contenido = pdf_a_imagen_png(archivo_contenido)
                media_type = 'image/png'
            except Exception as e:
                st.error(f"❌ No se pudo convertir el PDF '{nombre_archivo}': {e}")
                return {"emisor": "", "monto": "0", "destinatario": "", "id_operacion": "", "fecha": "", "horario": ""}
        elif tipo_archivo in ['image/jpeg', 'image/jpg']:
            media_type = 'image/jpeg'
        elif tipo_archivo == 'image/png':
            media_type = 'image/png'
        else:
            media_type = 'image/jpeg'

        base64_data = base64.b64encode(archivo_contenido).decode('utf-8')

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": '''Analiza este comprobante bancario y extrae EXACTAMENTE estos campos:

**IMPORTANTE - Reglas para el EMISOR:**
- El EMISOR es quien ENVÍA el dinero
- En Personal Pay: busca "De:" o el nombre al inicio
- En Ualá: busca "De" o "Enviaste desde"
- En Mercado Pago: busca "Enviaste dinero a"
- Si hay nombre y alias, usa el NOMBRE

**Campos:**
- emisor: Nombre de quien envía
- monto: Cantidad transferida
- destinatario: Nombre de quien recibe
- id_operacion: Código único de la operación
- fecha: YYYY-MM-DD
- horario: HH:MM:SS

Responde SOLO JSON válido, sin texto extra.

Ejemplo:
{
    "emisor": "Juan Pérez",
    "monto": "$1.500,00",
    "destinatario": "María González",
    "id_operacion": "123456789",
    "fecha": "2024-02-11",
    "horario": "14:30:00"
}'''
                    }
                ]
            }]
        )
        
        response_text = message.content[0].text.strip()
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        datos = json.loads(response_text)
        
        claves_requeridas = ["emisor", "monto", "destinatario", "id_operacion", "fecha", "horario"]
        for clave in claves_requeridas:
            if clave not in datos:
                datos[clave] = ""
        
        # Agregar monto limpio
        datos['monto_float'] = limpiar_monto(datos.get('monto', '0'))
        
        return datos
        
    except Exception as e:
        st.error(f"❌ Error al procesar: {str(e)}")
        return {"emisor": "", "monto": "0", "destinatario": "", "id_operacion": "", "fecha": "", "horario": "", "monto_float": 0.0}

def extraer_archivos_zip(archivo_zip: bytes) -> List[Tuple[str, bytes, str]]:
    """Extrae archivos de un ZIP"""
    archivos = []
    try:
        with zipfile.ZipFile(io.BytesIO(archivo_zip), 'r') as zip_ref:
            filelist_ordenada = sorted(zip_ref.filelist, key=lambda x: x.filename)
            
            for file_info in filelist_ordenada:
                if not file_info.is_dir():
                    nombre = file_info.filename
                    
                    # Ignorar archivos de macOS
                    if '__MACOSX' in nombre or nombre.startswith('.'):
                        continue
                    
                    contenido = zip_ref.read(nombre)
                    extension = Path(nombre).suffix.lower()
                    
                    if extension in ['.jpg', '.jpeg']:
                        tipo_mime = 'image/jpeg'
                    elif extension == '.png':
                        tipo_mime = 'image/png'
                    elif extension == '.pdf':
                        tipo_mime = 'application/pdf'
                    else:
                        continue
                    
                    archivos.append((nombre, contenido, tipo_mime))
    except Exception as e:
        st.error(f"❌ Error al extraer ZIP: {str(e)}")
    
    return archivos

def similitud_textos(a, b):
    """Calcula similitud entre dos textos"""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

# =============================================================================
# FUNCIONES DE DOBLE PARTIDA (EXTRACTOR)
# =============================================================================

def generar_doble_partida(emisor: str, monto: str, id_op: str, cliente: str) -> Dict[str, str]:
    """Genera líneas de doble partida según el cliente"""
    resultado = {}
    
    # NEXO (siempre igual)
    resultado["nexo"] = f'"{emisor}",,,,,,,,{monto}'
    
    # CLIENTE (varía según quién sea)
    if cliente == "Celso":
        resultado["cliente"] = f'"{emisor}",{id_op},,,,,,,,,{monto}'
    else:
        resultado["cliente"] = f'"{emisor}",,,,,{monto}'
    
    return resultado

# =============================================================================
# CSS PROFESIONAL
# =============================================================================

def cargar_css():
    """Carga CSS personalizado"""
    st.markdown("""
    <style>
        /* Tema General */
        .main {
            background-color: #f8f9fa;
        }
        
        /* Título Principal */
        h1 {
            color: #1e3a5f;
            font-weight: 700;
            padding-bottom: 1rem;
            border-bottom: 3px solid #4CAF50;
        }
        
        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background-color: white;
            padding: 10px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .stTabs [data-baseweb="tab"] {
            background-color: #e9ecef;
            border-radius: 8px;
            padding: 10px 20px;
            font-weight: 600;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #4CAF50 !important;
            color: white !important;
        }
        
        /* Métricas y KPIs */
        [data-testid="stMetricValue"] {
            font-size: 2rem;
            font-weight: 700;
        }
        
        /* Botones */
        .stButton button {
            background-color: #4CAF50;
            color: white;
            border-radius: 8px;
            border: none;
            padding: 0.5rem 2rem;
            font-weight: 600;
            transition: all 0.3s;
        }
        
        .stButton button:hover {
            background-color: #45a049;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
        
        /* Cajas de Código */
        .stCodeBlock {
            background-color: #f1f3f5;
            border-left: 4px solid #4CAF50;
            padding: 1rem;
            border-radius: 8px;
        }
        
        /* Alerts */
        .stAlert {
            border-radius: 8px;
            padding: 1rem;
        }
        
        /* Selectbox y Inputs */
        .stSelectbox, .stTextInput {
            border-radius: 8px;
        }
        
        /* Expander */
        .streamlit-expanderHeader {
            background-color: white;
            border-radius: 8px;
            font-weight: 600;
        }
        
        /* Tablas */
        .dataframe {
            border-radius: 8px;
            overflow: hidden;
        }
        
        /* Semáforos personalizados */
        .semaforo {
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            font-weight: bold;
            margin: 10px 0;
        }
        
        .semaforo-verde {
            background-color: #d4edda;
            color: #155724;
            border: 2px solid #28a745;
        }
        
        .semaforo-amarillo {
            background-color: #fff3cd;
            color: #856404;
            border: 2px solid #ffc107;
        }
        
        .semaforo-rojo {
            background-color: #f8d7da;
            color: #721c24;
            border: 2px solid #dc3545;
        }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# TAB 1: CONTROL Y CONCILIACIONES
# =============================================================================

def tab_control():
    """Tab principal de Control y Conciliaciones"""
    
    st.header("📊 Control y Conciliaciones")
    
    # Selector de fecha
    col_fecha1, col_fecha2 = st.columns([3, 1])
    with col_fecha1:
        fecha_seleccionada = st.date_input(
            "📅 Fecha a consultar",
            value=datetime.now(),
            format="DD/MM/YYYY"
        )
    
    dia_formato = fecha_seleccionada.strftime("%d/%m/%Y")
    
    # Conectar a BD
    conn = get_db_connection()
    
    # === SECCIÓN 1: SEMÁFOROS DE DIFERENCIA CERO ===
    st.subheader("🚥 Semáforos - Diferencia Cero")
    
    # Obtener datos de Nexo
    saldos = conn.execute("SELECT * FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone()
    nexo_ingresos = saldos['nexo_ingresos'] if saldos else 0
    nexo_egresos = saldos['nexo_egresos'] if saldos else 0
    
    # Calcular datos del sistema
    sis_ingresos = conn.execute(
        "SELECT SUM(monto) FROM transacciones WHERE tipo='ENTRADA' AND fecha_pedido LIKE ?",
        (f'{dia_formato}%',)
    ).fetchone()[0] or 0
    
    sis_egresos = conn.execute(
        "SELECT SUM(monto) FROM transacciones WHERE tipo='SALIDA' AND estado='COMPLETADO' AND fecha_pedido LIKE ?",
        (f'{dia_formato}%',)
    ).fetchone()[0] or 0
    
    # Calcular comisión automática (0.75%)
    comision_egresos = sis_egresos * 0.0075
    total_sis_egresos = sis_egresos + comision_egresos
    
    # Diferencias
    dif_ingresos = nexo_ingresos - sis_ingresos
    dif_egresos = nexo_egresos - total_sis_egresos
    
    # Mostrar semáforos
    col_ing, col_egr = st.columns(2)
    
    with col_ing:
        st.markdown("### 💰 Ingresos")
        color_ing = "verde" if abs(dif_ingresos) < 1 else ("amarillo" if abs(dif_ingresos) < 1000 else "rojo")
        st.markdown(f"""
        <div class="semaforo semaforo-{color_ing}">
            <h4>Nexo Declara: ${nexo_ingresos:,.2f}</h4>
            <h4>Sistema Suma: ${sis_ingresos:,.2f}</h4>
            <h2>Diferencia: ${dif_ingresos:,.2f}</h2>
        </div>
        """, unsafe_allow_html=True)
        
        # Formulario para actualizar Nexo Ingresos
        with st.expander("✏️ Actualizar dato de Nexo"):
            new_ing = st.number_input("Nexo Ingresos", value=float(nexo_ingresos), key="nexo_ing")
            if st.button("💾 Guardar Ingresos", key="btn_ing"):
                row = conn.execute("SELECT fecha FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone()
                if row:
                    conn.execute("UPDATE saldos_diarios SET nexo_ingresos = ? WHERE fecha = ?", (new_ing, dia_formato))
                else:
                    conn.execute("INSERT INTO saldos_diarios (fecha, nexo_ingresos, nexo_egresos) VALUES (?, ?, ?)",
                               (dia_formato, new_ing, 0))
                conn.commit()
                st.success("✅ Actualizado")
                st.rerun()
    
    with col_egr:
        st.markdown("### 💸 Egresos")
        color_egr = "verde" if abs(dif_egresos) < 1 else ("amarillo" if abs(dif_egresos) < 1000 else "rojo")
        st.markdown(f"""
        <div class="semaforo semaforo-{color_egr}">
            <h4>Nexo Declara: ${nexo_egresos:,.2f}</h4>
            <h4>Sistema Suma: ${sis_egresos:,.2f}</h4>
            <h4>Comisión 0.75%: ${comision_egresos:,.2f}</h4>
            <h4>Total: ${total_sis_egresos:,.2f}</h4>
            <h2>Diferencia: ${dif_egresos:,.2f}</h2>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("✏️ Actualizar dato de Nexo"):
            new_egr = st.number_input("Nexo Egresos", value=float(nexo_egresos), key="nexo_egr")
            if st.button("💾 Guardar Egresos", key="btn_egr"):
                row = conn.execute("SELECT fecha FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone()
                if row:
                    conn.execute("UPDATE saldos_diarios SET nexo_egresos = ? WHERE fecha = ?", (new_egr, dia_formato))
                else:
                    conn.execute("INSERT INTO saldos_diarios (fecha, nexo_ingresos, nexo_egresos) VALUES (?, ?, ?)",
                               (dia_formato, 0, new_egr))
                conn.commit()
                st.success("✅ Actualizado")
                st.rerun()
    
    st.markdown("---")
    
    # === SECCIÓN 2: FONDEO (INGRESOS) ===
    st.subheader("📥 Fondeo - Ingresos")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        cliente_fondeo = st.selectbox("📌 ¿De quién es el fondeo?", CLIENTES_CONTROL, key="select_fondeo")
    
    with col2:
        archivos_fondeo = st.file_uploader(
            "📎 Subir comprobantes de fondeo (ZIP, JPG, PNG, PDF)",
            type=['zip', 'jpg', 'jpeg', 'png', 'pdf'],
            accept_multiple_files=True,
            key="upload_fondeo"
        )
    
    if st.button("🚀 Procesar Fondeos", type="primary", key="btn_fondeo"):
        if not archivos_fondeo:
            st.warning("⚠️ No subiste archivos")
        else:
            # Extraer archivos
            archivos_a_procesar = []
            for archivo in archivos_fondeo:
                contenido = archivo.read()
                nombre = archivo.name
                tipo = archivo.type
                
                if nombre.lower().endswith('.zip'):
                    archivos_zip = extraer_archivos_zip(contenido)
                    archivos_a_procesar.extend(archivos_zip)
                else:
                    archivos_a_procesar.append((nombre, contenido, tipo))
            
            if archivos_a_procesar:
                progress_bar = st.progress(0)
                status_text = st.empty()
                exitosos = 0
                duplicados = 0
                
                for idx, (nombre, contenido, tipo_mime) in enumerate(archivos_a_procesar):
                    progress = (idx + 1) / len(archivos_a_procesar)
                    progress_bar.progress(progress)
                    status_text.text(f"Procesando {idx + 1}/{len(archivos_a_procesar)}: {nombre}")
                    
                    try:
                        datos = extraer_datos_con_vision_api(contenido, nombre, tipo_mime)
                        
                        # Generar ID si no existe
                        id_op = datos.get('id_operacion', '')
                        if not id_op or str(id_op).strip() == "":
                            id_op = f"SIN_ID_{datetime.now().strftime('%H%M%S')}"
                        else:
                            id_op = str(id_op).strip()
                        
                        # Chequeo de duplicados
                        if "SIN_ID" not in id_op:
                            existe = conn.execute(
                                "SELECT id FROM transacciones WHERE id_operacion = ? AND tipo = 'ENTRADA'",
                                (id_op,)
                            ).fetchone()
                            
                            if existe:
                                duplicados += 1
                                continue
                        
                        emisor = datos.get('emisor', '') or id_op
                        monto_float = datos.get('monto_float', 0.0)
                        
                        if monto_float <= 0:
                            st.warning(f"⚠️ {nombre}: Monto inválido o 0")
                            continue
                        
                        # Guardar en BD
                        conn.execute(
                            "INSERT INTO transacciones (tipo, solicitante, titular, monto, estado, fecha_pedido, id_operacion) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            ("ENTRADA", cliente_fondeo, emisor, monto_float, "COMPLETADO", datetime.now().strftime("%d/%m/%Y %H:%M"), id_op)
                        )
                        exitosos += 1
                        
                        time.sleep(0.5)
                        
                    except Exception as e:
                        st.error(f"❌ Error en {nombre}: {str(e)}")
                
                conn.commit()
                progress_bar.empty()
                status_text.empty()
                
                if exitosos > 0:
                    st.success(f"✅ {exitosos} fondeo(s) procesado(s)")
                if duplicados > 0:
                    st.warning(f"⚠️ {duplicados} comprobante(s) duplicado(s) ignorado(s)")
                
                st.rerun()
    
    st.markdown("---")
    
    # === SECCIÓN 3: MOSTRADOR (EGRESOS) ===
    st.subheader("📤 Mostrador - Egresos y Pedidos")
    
    # Formulario para anotar pedido manual
    with st.expander("➕ Anotar Pedido Manual"):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            solicitante = st.selectbox("Cliente", CLIENTES_CONTROL, key="manual_sol")
        
        with col2:
            sub_cliente = st.text_input("Sub-cliente (opcional)", key="manual_sub")
        
        with col3:
            titular = st.text_input("Titular", key="manual_tit")
        
        with col4:
            monto_manual = st.text_input("Monto", key="manual_monto")
        
        if st.button("💾 Guardar Pedido", key="btn_manual"):
            if titular and monto_manual:
                try:
                    monto_float = limpiar_monto(monto_manual)
                    estado = "COMPLETADO" if solicitante == 'Ajustes Manuales' else "PENDIENTE"
                    
                    conn.execute(
                        "INSERT INTO transacciones (tipo, solicitante, sub_cliente, titular, monto, estado, fecha_pedido) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ("SALIDA", solicitante, sub_cliente, titular, monto_float, estado, datetime.now().strftime("%d/%m/%Y %H:%M"))
                    )
                    conn.commit()
                    st.success("✅ Pedido anotado")
                    st.rerun()
                except:
                    st.error("❌ Monto inválido")
            else:
                st.warning("⚠️ Completá titular y monto")
    
    # Match automático con comprobantes
    st.markdown("### 🔍 Buscar Matches Automáticos")
    
    archivos_match = st.file_uploader(
        "📎 Subir comprobantes de transferencias realizadas",
        type=['zip', 'jpg', 'jpeg', 'png', 'pdf'],
        accept_multiple_files=True,
        key="upload_match"
    )
    
    if st.button("🎯 Buscar Matches", key="btn_match"):
        if not archivos_match:
            st.warning("⚠️ No subiste archivos")
        else:
            archivos_a_procesar = []
            for archivo in archivos_match:
                contenido = archivo.read()
                nombre = archivo.name
                tipo = archivo.type
                
                if nombre.lower().endswith('.zip'):
                    archivos_zip = extraer_archivos_zip(contenido)
                    archivos_a_procesar.extend(archivos_zip)
                else:
                    archivos_a_procesar.append((nombre, contenido, tipo))
            
            if archivos_a_procesar:
                progress_bar = st.progress(0)
                status_text = st.empty()
                matches_encontrados = 0
                
                for idx, (nombre, contenido, tipo_mime) in enumerate(archivos_a_procesar):
                    progress = (idx + 1) / len(archivos_a_procesar)
                    progress_bar.progress(progress)
                    status_text.text(f"Analizando {idx + 1}/{len(archivos_a_procesar)}: {nombre}")
                    
                    try:
                        datos = extraer_datos_con_vision_api(contenido, nombre, tipo_mime)
                        monto = datos.get('monto_float', 0.0)
                        dest = datos.get('destinatario', '')
                        id_op = datos.get('id_operacion', '')
                        
                        # Chequear duplicados
                        if id_op:
                            existe = conn.execute(
                                "SELECT id FROM transacciones WHERE id_operacion = ? AND estado = 'COMPLETADO'",
                                (id_op,)
                            ).fetchone()
                            
                            if existe:
                                continue
                        
                        # Buscar pendientes con mismo monto
                        posibles = conn.execute(
                            "SELECT * FROM transacciones WHERE estado = 'PENDIENTE' AND monto = ?",
                            (monto,)
                        ).fetchall()
                        
                        if posibles:
                            # Buscar el mejor match por nombre
                            mejor = max(posibles, key=lambda p: similitud_textos(p['titular'], dest))
                            similitud = similitud_textos(mejor['titular'], dest)
                            
                            nivel = 'AMARILLO' if not dest or similitud < 0.4 else 'VERDE'
                            
                            conn.execute(
                                "UPDATE transacciones SET estado = 'SUGERIDO', nivel_alerta = ?, datos_extraidos = ?, id_operacion = ? WHERE id = ?",
                                (nivel, f"Leído: '{dest or 'N/A'}'", id_op, mejor['id'])
                            )
                            matches_encontrados += 1
                        
                        time.sleep(0.5)
                        
                    except Exception as e:
                        st.error(f"❌ Error en {nombre}: {str(e)}")
                
                conn.commit()
                progress_bar.empty()
                status_text.empty()
                
                if matches_encontrados > 0:
                    st.success(f"✅ {matches_encontrados} match(es) encontrado(s)")
                else:
                    st.info("ℹ️ No se encontraron matches")
                
                st.rerun()
    
    # Tabla de pendientes/sugeridos
    st.markdown("### 📋 Transferencias Pendientes y Sugeridas")
    
    salidas = conn.execute(
        "SELECT * FROM transacciones WHERE tipo = 'SALIDA' AND (fecha_pedido LIKE ? OR estado IN ('PENDIENTE', 'SUGERIDO')) ORDER BY estado DESC, id DESC",
        (f'{dia_formato}%',)
    ).fetchall()
    
    if salidas:
        for salida in salidas:
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 2, 1])
            
            with col1:
                st.write(f"**{salida['solicitante']}**")
                if salida['sub_cliente']:
                    st.caption(salida['sub_cliente'])
            
            with col2:
                st.write(salida['titular'])
            
            with col3:
                st.write(f"${salida['monto']:,.2f}")
            
            with col4:
                if salida['estado'] == 'PENDIENTE':
                    st.warning("⏳ Pendiente")
                elif salida['estado'] == 'SUGERIDO':
                    color = "🟡" if salida['nivel_alerta'] == 'AMARILLO' else "🟢"
                    st.info(f"{color} Sugerido")
                    if salida['datos_extraidos']:
                        st.caption(salida['datos_extraidos'])
            
            with col5:
                if salida['estado'] == 'SUGERIDO':
                    if st.button("✅", key=f"ok_{salida['id']}"):
                        conn.execute("UPDATE transacciones SET estado = 'COMPLETADO' WHERE id = ?", (salida['id'],))
                        conn.commit()
                        st.rerun()
                    
                    if st.button("❌", key=f"no_{salida['id']}"):
                        conn.execute(
                            "UPDATE transacciones SET estado = 'PENDIENTE', nivel_alerta = NULL, datos_extraidos = NULL, id_operacion = NULL WHERE id = ?",
                            (salida['id'],)
                        )
                        conn.commit()
                        st.rerun()
                
                if st.button("🗑️", key=f"del_{salida['id']}"):
                    conn.execute("DELETE FROM transacciones WHERE id = ?", (salida['id'],))
                    conn.commit()
                    st.rerun()
    else:
        st.info("ℹ️ No hay transferencias pendientes")
    
    st.markdown("---")
    
    # === SECCIÓN 4: AUDITORÍA GENERAL ===
    st.subheader("📋 Auditoría General")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        filtro_tipo = st.selectbox("Tipo", ["TODOS", "ENTRADA", "SALIDA"], key="filtro_tipo")
    
    with col2:
        filtro_cliente = st.selectbox("Cliente", ["TODOS"] + CLIENTES_CONTROL, key="filtro_cliente")
    
    with col3:
        buscar_texto = st.text_input("🔍 Buscar en titular", key="buscar")
    
    # Construir query
    query = "SELECT * FROM transacciones WHERE 1=1"
    params = []
    
    if filtro_tipo != "TODOS":
        query += " AND tipo = ?"
        params.append(filtro_tipo)
    
    if filtro_cliente != "TODOS":
        query += " AND solicitante = ?"
        params.append(filtro_cliente)
    
    if buscar_texto:
        query += " AND titular LIKE ?"
        params.append(f"%{buscar_texto}%")
    
    query += " ORDER BY id DESC LIMIT 100"
    
    resultados = conn.execute(query, params).fetchall()
    
    if resultados:
        st.write(f"📊 {len(resultados)} transacciones encontradas")
        
        # Mostrar como tabla
        datos_tabla = []
        for r in resultados:
            datos_tabla.append({
                "ID": r['id'],
                "Tipo": r['tipo'],
                "Cliente": r['solicitante'],
                "Titular": r['titular'],
                "Monto": f"${r['monto']:,.2f}",
                "Estado": r['estado'],
                "Fecha": r['fecha_pedido']
            })
        
        st.dataframe(datos_tabla, use_container_width=True)
        
        # Botón para eliminar seleccionados
        if st.button("🗑️ Eliminar todas las transacciones mostradas", key="btn_delete_all"):
            if st.checkbox("⚠️ Confirmar eliminación", key="confirm_delete"):
                ids = [r['id'] for r in resultados]
                conn.execute(f'DELETE FROM transacciones WHERE id IN ({",".join(["?"] * len(ids))})', ids)
                conn.commit()
                st.success(f"✅ {len(ids)} transacciones eliminadas")
                st.rerun()
    else:
        st.info("ℹ️ No hay resultados")
    
    conn.close()

# =============================================================================
# TAB 2: EXTRACTOR + DOBLE PARTIDA
# =============================================================================

def tab_extractor():
    """Tab de Extractor y Doble Partida"""
    
    st.header("🔄 Extractor + Doble Partida")
    
    st.markdown("""
    Este módulo procesa comprobantes y genera automáticamente las líneas para:
    - **Hoja NEXO** (todos los clientes)
    - **Hoja del CLIENTE** (según formato específico)
    """)
    
    # PASO 1: Seleccionar cliente
    st.subheader("1️⃣ Seleccionar Cliente")
    cliente_seleccionado = st.selectbox(
        "¿De quién son estos comprobantes?",
        ["Seleccionar..."] + CLIENTES_EXTRACTOR,
        help="Seleccioná el cliente emisor para generar la doble partida correcta"
    )
    
    # PASO 2: Cargar archivos
    st.subheader("2️⃣ Cargar Comprobantes")
    archivos_subidos = st.file_uploader(
        "Selecciona uno o más archivos (imágenes, PDFs o ZIPs)",
        type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
        accept_multiple_files=True,
        help="Los archivos ZIP serán extraídos automáticamente",
        key="extractor_upload"
    )
    
    # PASO 3: Procesar
    if archivos_subidos and cliente_seleccionado != "Seleccionar...":
        if st.button("🚀 Procesar Comprobantes", type="primary", key="btn_extractor"):
            
            # Extraer archivos
            with st.spinner("Extrayendo archivos..."):
                archivos_a_procesar = []
                for archivo in archivos_subidos:
                    contenido = archivo.read()
                    nombre = archivo.name
                    tipo = archivo.type
                    
                    if nombre.lower().endswith('.zip'):
                        archivos_zip = extraer_archivos_zip(contenido)
                        archivos_a_procesar.extend(archivos_zip)
                    else:
                        archivos_a_procesar.append((nombre, contenido, tipo))
            
            if not archivos_a_procesar:
                st.error("❌ No se encontraron archivos válidos")
            else:
                st.success(f"✅ {len(archivos_a_procesar)} archivo(s) detectado(s)")
                
                # Procesar cada archivo
                resultados = []
                datos_completos = []
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for idx, (nombre, contenido, tipo_mime) in enumerate(archivos_a_procesar):
                    progress = (idx + 1) / len(archivos_a_procesar)
                    progress_bar.progress(progress)
                    status_text.text(f"Procesando {idx + 1}/{len(archivos_a_procesar)}: {nombre}")
                    
                    # Extraer datos
                    datos_extraidos = extraer_datos_con_vision_api(contenido, nombre, tipo_mime)
                    
                    # Limpiar datos
                    emisor = limpiar_nombre(datos_extraidos.get("emisor", ""))
                    if not emisor:
                        id_op = datos_extraidos.get("id_operacion", "")
                        emisor = id_op if id_op else "SIN_EMISOR"
                    
                    monto_str = str(datos_extraidos.get('monto_float', 0.0)).replace('.', ',')
                    id_operacion = datos_extraidos.get("id_operacion", "")
                    
                    resultado = {
                        "archivo": nombre,
                        "emisor": emisor,
                        "monto": monto_str,
                        "id_operacion": id_operacion,
                        "datos_raw": datos_extraidos
                    }
                    
                    resultados.append(resultado)
                    datos_completos.append(datos_extraidos)
                    
                    time.sleep(0.5)
                
                progress_bar.empty()
                status_text.empty()
                
                # Detectar duplicados
                ids_vistos = {}
                duplicados = []
                
                for item in datos_completos:
                    id_op = item.get("id_operacion", "")
                    if id_op and id_op.strip():
                        if id_op in ids_vistos:
                            if id_op not in duplicados:
                                duplicados.append(id_op)
                        else:
                            ids_vistos[id_op] = True
                
                # Filtrar duplicados
                resultados_sin_duplicados = []
                ids_ya_vistos = set()
                
                for resultado in resultados:
                    id_op = resultado["id_operacion"]
                    if id_op and id_op in duplicados:
                        if id_op not in ids_ya_vistos:
                            ids_ya_vistos.add(id_op)
                            resultados_sin_duplicados.append(resultado)
                    else:
                        resultados_sin_duplicados.append(resultado)
                
                if duplicados:
                    eliminados = len(resultados) - len(resultados_sin_duplicados)
                    st.warning(f"⚠️ {eliminados} duplicado(s) eliminado(s) (IDs: {', '.join(duplicados)})")
                
                # Generar doble partida
                lineas_nexo = []
                lineas_cliente = []
                
                for resultado in resultados_sin_duplicados:
                    doble_partida = generar_doble_partida(
                        resultado["emisor"],
                        resultado["monto"],
                        resultado["id_operacion"],
                        cliente_seleccionado
                    )
                    lineas_nexo.append(doble_partida["nexo"])
                    lineas_cliente.append(doble_partida["cliente"])
                
                # Mostrar resultados
                st.success(f"✅ {len(resultados_sin_duplicados)} comprobantes procesados")
                
                st.subheader("3️⃣ Resultados - Copiar y Pegar")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### 📊 Hoja NEXO")
                    output_nexo = "\n".join(lineas_nexo)
                    st.code(output_nexo, language=None)
                    st.download_button(
                        label="💾 Descargar NEXO",
                        data=output_nexo,
                        file_name=f"nexo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain",
                        key="btn_nexo_dl"
                    )
                
                with col2:
                    st.markdown(f"### 📊 Hoja {cliente_seleccionado.upper()}")
                    output_cliente = "\n".join(lineas_cliente)
                    st.code(output_cliente, language=None)
                    st.download_button(
                        label=f"💾 Descargar {cliente_seleccionado.upper()}",
                        data=output_cliente,
                        file_name=f"{cliente_seleccionado.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain",
                        key="btn_cliente_dl"
                    )
                
                # Detalle
                with st.expander("🔍 Ver Detalle de Comprobantes"):
                    for idx, resultado in enumerate(resultados_sin_duplicados, 1):
                        st.markdown(f"**#{idx} - {resultado['archivo']}**")
                        st.json(resultado['datos_raw'])
                        st.markdown("---")
    
    elif archivos_subidos and cliente_seleccionado == "Seleccionar...":
        st.warning("⚠️ Por favor, seleccioná un cliente antes de procesar")

# =============================================================================
# APLICACIÓN PRINCIPAL
# =============================================================================

def main():
    """Función principal"""
    
    # Cargar CSS
    cargar_css()
    
    # Inicializar BD
    init_db()
    
    # Título principal
    st.title("🏦 Sistema Sidera Unificado")
    st.markdown("**Control de Conciliaciones + Extractor de Comprobantes**")
    
    # Verificar API Key
    api_key = st.secrets.get("ANTHROPIC_API_KEY", None) if hasattr(st, "secrets") else None
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    
    # Sidebar
    with st.sidebar:
        st.header("ℹ️ Información")
        
        if api_key:
            st.success("✅ API Key configurada")
        else:
            st.error("⚠️ API Key NO configurada")
        
        st.markdown("---")
        
        st.markdown("""
        **Módulos disponibles:**
        
        📊 **Control y Conciliaciones:**
        - Semáforos Diferencia Cero
        - Fondeo (Ingresos)
        - Mostrador (Egresos)
        - Auditoría General
        
        🔄 **Extractor + Doble Partida:**
        - Procesamiento automático
        - Salida para NEXO + CLIENTE
        - Detección de duplicados
        
        **Modelo IA:** Claude Sonnet 4.6
        """)
        
        st.markdown("---")
        st.caption("💡 Sistema Sidera v2.0 | Marzo 2026")
    
    # Tabs principales
    tab1, tab2 = st.tabs(["📊 Control y Conciliaciones", "🔄 Extractor + Doble Partida"])
    
    with tab1:
        tab_control()
    
    with tab2:
        tab_extractor()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: gray; font-size: 0.9em;'>
        💡 Desarrollado por y para SIDERA | Sistema Unificado de Gestión
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
