import os
import zipfile
import re
import xml.etree.ElementTree as ET
import folium
import branca.colormap as bcm
from folium.plugins import PolyLineTextPath
from flask import Flask, render_template, request
import time
import math

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ================================
# FUNÇÃO PARA LER KMZ
# ================================
def extrair_pontos_kmz(caminho_kmz):

    with zipfile.ZipFile(caminho_kmz, 'r') as z:
        nome_kml = [f for f in z.namelist() if f.endswith('.kml')][0]
        kml_bytes = z.read(nome_kml)

    kml_text = kml_bytes.decode("utf-8")

    # Corrigir vírgula decimal
    kml_text = re.sub(r'(\d),(\d)', r'\1.\2', kml_text)

    root = ET.fromstring(kml_text)
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    pontos = []

    for placemark in root.findall(".//kml:Placemark", ns):

        nome = placemark.find("kml:name", ns)
        coord = placemark.find(".//kml:coordinates", ns)

        if nome is None or coord is None:
            continue

        coord_text = coord.text.strip()
        partes = coord_text.split(",")

        if len(partes) < 2:
            continue

        lon_raw = partes[0]
        lat_raw = partes[1]

        def limpar_numero(valor):
            valor = re.sub(r"[^0-9\.-]", "", valor)
            if valor.count(".") > 1:
                p = valor.split(".")
                valor = p[0] + "." + "".join(p[1:])
            return float(valor)

        try:
            lon = limpar_numero(lon_raw)
            lat = limpar_numero(lat_raw)
        except:
            continue

        pontos.append({
            "nome": nome.text.strip(),
            "lat": lat,
            "lon": lon
        })

    # Ordenar pela sequência (se nome começar com número)
    def extrair_seq(nome):
        try:
            return int(nome.split()[0])
        except:
            return 9999

    pontos = sorted(pontos, key=lambda x: extrair_seq(x["nome"]))

    return pontos


# ================================
# GERAR MAPA
# ================================
def gerar_mapa(pontos):

    mapa = folium.Map(
        location=[pontos[0]["lat"], pontos[0]["lon"]],
        zoom_start=14,
        tiles="OpenStreetMap"
    )

    coords = [(p["lat"], p["lon"]) for p in pontos]
    total = len(coords)

    colormap = bcm.LinearColormap(
        colors=["green", "yellow", "red"],
        vmin=1,
        vmax=total
    )

    for i, p in enumerate(pontos, start=1):

        cor = colormap(i)

        if i == 1:
            tamanho = 30
            borda = "darkgreen"
        elif i == total:
            tamanho = 30
            borda = "darkred"
        else:
            tamanho = 22
            borda = cor

        html_icon = f"""
        <div style="
            background:{cor};
            width:{tamanho}px;
            height:{tamanho}px;
            border-radius:50%;
            text-align:center;
            color:white;
            font-weight:bold;
            line-height:{tamanho}px;
            border:2px solid {borda};
        ">
            {i}
        </div>
        """

        folium.Marker(
            location=[p["lat"], p["lon"]],
            icon=folium.DivIcon(html=html_icon),
            tooltip=f"<b>Sequência:</b> {i}<br>{p['nome']}"
        ).add_to(mapa)

    linha = folium.PolyLine(
        coords,
        color="blue",
        weight=4,
        opacity=0.7
    ).add_to(mapa)

    PolyLineTextPath(
        linha,
        "➜ ",
        repeat=True,
        offset=7,
        attributes={"fill": "blue", "font-weight": "bold", "font-size": "16"}
    ).add_to(mapa)

    colormap.caption = "Ordem da Entrega"
    colormap.add_to(mapa)

    return mapa._repr_html_()

# ===============================
# IDENTIFICAR O PADRÃO
# ===============================

def calcular_distancia(p1, p2):
    return math.sqrt(
        (p1["lat"] - p2["lat"])**2 +
        (p1["lon"] - p2["lon"])**2
    )

def identificar_padrao(pontos):

    origem = pontos[0]

    distancias = [
        calcular_distancia(origem, p)
        for p in pontos
    ]

    indice_max = distancias.index(max(distancias))

    crescente = all(
        distancias[i] <= distancias[i+1]
        for i in range(indice_max)
    )

    decrescente = all(
        distancias[i] >= distancias[i+1]
        for i in range(indice_max, len(distancias)-1)
    )

    if crescente and decrescente:
        return "Padrão Vai até o extremo e retorna"
    elif crescente:
        return "Padrão Linear Progressivo"
    else:
        return "Padrão Irregular / Zig-Zag"


# ================================
# ROTAS FLASK
# ================================
@app.route("/", methods=["GET", "POST"])
def index():

    pontos1 = []
    pontos2 = []

    mapa1 = None
    mapa2 = None
    info1 = None
    info2 = None

    if request.method == "POST":

        arquivo1 = request.files.get("rota1")
        arquivo2 = request.files.get("rota2")

        # ================= ROTA 1 =================
        if arquivo1 and arquivo1.filename.endswith(".kmz"):

            nome_unico1 = f"rota1_{int(time.time()*1000)}.kmz"
            caminho1 = os.path.join(app.config["UPLOAD_FOLDER"], nome_unico1)

            arquivo1.save(caminho1)

            pontos1 = extrair_pontos_kmz(caminho1)

            if pontos1:
                mapa1 = gerar_mapa(pontos1)
                info1 = len(pontos1)

        # ================= ROTA 2 =================
        if arquivo2 and arquivo2.filename.endswith(".kmz"):

            nome_unico2 = f"rota2_{int(time.time()*1000)}.kmz"
            caminho2 = os.path.join(app.config["UPLOAD_FOLDER"], nome_unico2)

            arquivo2.save(caminho2)

            pontos2 = extrair_pontos_kmz(caminho2)

            if pontos2:
                mapa2 = gerar_mapa(pontos2)
                info2 = len(pontos2)

    padrao1 = None
    padrao2 = None

    if len(pontos1) > 1:
        padrao1 = identificar_padrao(pontos1)

    if len(pontos2) > 1:
        padrao2 = identificar_padrao(pontos2)
            

    return render_template(
        "index.html",
        mapa1=mapa1,
        mapa2=mapa2,
        info1=info1,
        info2=info2,
        padrao1=padrao1,
        padrao2=padrao2
    )

if __name__ == "__main__":
    app.run(debug=True)