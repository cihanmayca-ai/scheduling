import streamlit as st
import sqlite3
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Vardiya Sistemi", page_icon="⛽", layout="wide")

# --- CSS ---
st.markdown("""
<style>
    .shift-table { width: 100%; border-collapse: collapse; font-family: sans-serif; background-color: #1E1E1E; }
    .shift-table th, .shift-table td { border: 1px solid #333; padding: 10px; }
    .pompa { color: #3498db; font-weight: bold; }
    .market { color: #e67e22; font-weight: bold; }
    .izinli { color: #e74c3c; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# --- Veritabanı ---
def veritabanini_hazirla():
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    cursor = baglanti.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS Personeller (id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT, rol TEXT, aktif_mi INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS VardiyaKayitlari (id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER, tarih TEXT, hafta_numarasi INTEGER, vardiya_tipi TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS Ayarlar (kural_key TEXT PRIMARY KEY, aktif_mi INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS Izinler (id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER, tarih TEXT)''')

    # Varsayılan Kurallar
    varsayilanlar = [("gece_market_zorunlu", 0), ("gecen_hafta_gece_kisiti", 1), ("market_haftasonu_calisir", 1)]
    for k, v in varsayilanlar: cursor.execute("INSERT OR IGNORE INTO Ayarlar VALUES (?, ?)", (k, v))
    baglanti.commit()
    baglanti.close()

veritabanini_hazirla()

def get_kural(kural_key):
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    val = baglanti.execute("SELECT aktif_mi FROM Ayarlar WHERE kural_key=?", (kural_key,)).fetchone()[0]
    baglanti.close()
    return val == 1

# --- Arayüz ---
st.sidebar.title("⛽ Benzinlik Yönetimi")
menu = st.sidebar.radio("Menü", ["📅 Yeni Vardiya Üret", "🏖️ İzin Planlama", "⚙️ Kural Ayarları", "🗂️ Geçmiş Vardiyalar", "👥 Personel Listesi"])

if menu == "🏖️ İzin Planlama":
    st.title("🏖️ İzin Planlama")
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    personeller = pd.read_sql_query("SELECT id, ad_soyad FROM Personeller WHERE aktif_mi=1", baglanti)

    with st.form("izin_form"):
        p_sec = st.selectbox("Personel Seç:", personeller['ad_soyad'].tolist())
        tarih_sec = st.date_input("İzin Günü:")
        if st.form_submit_button("İzinli İşaretle"):
            p_id = personeller[personeller['ad_soyad'] == p_sec]['id'].values[0]
            baglanti.execute("INSERT INTO Izinler (personel_id, tarih) VALUES (?, ?)", (int(p_id), tarih_sec.strftime('%Y-%m-%d')))
            baglanti.commit()
            st.success(f"{p_sec} için {tarih_sec} tarihi izinli olarak kaydedildi.")

    st.markdown("### Kayıtlı İzinler")
    izinler = pd.read_sql_query("SELECT p.ad_soyad, i.tarih FROM Izinler i JOIN Personeller p ON i.personel_id = p.id", baglanti)
    st.dataframe(izinler)
    baglanti.close()

elif menu == "⚙️ Kural Ayarları":
    st.title("⚙️ Kural Ayarları")
    kural_map = {"gece_market_zorunlu": "Gece vardiyasında mutlaka 1 Market çalışanı olsun", "gecen_hafta_gece_kisiti": "Geçen hafta gece çalışan bu hafta gece çalışamasın", "market_haftasonu_calisir": "Market çalışanları hafta sonu da çalışsın"}
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    for key, label in kural_map.items():
        durum = get_kural(key)
        if st.toggle(label, value=durum): baglanti.execute("UPDATE Ayarlar SET aktif_mi=1 WHERE kural_key=?", (key,))
        else: baglanti.execute("UPDATE Ayarlar SET aktif_mi=0 WHERE kural_key=?", (key,))
    baglanti.commit()
    baglanti.close()

elif menu == "👥 Personel Listesi":
    st.title("👥 Personel")
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    df = pd.read_sql_query("SELECT id, ad_soyad, rol, aktif_mi FROM Personeller", baglanti)
    baglanti.close()
    edited_df = st.data_editor(df, use_container_width=True)
    if st.button("💾 Kaydet"):
        baglanti = sqlite3.connect('vardiya_sistemi.db')
        for i, row in edited_df.iterrows():
            baglanti.execute("UPDATE Personeller SET ad_soyad=?, rol=?, aktif_mi=? WHERE id=?", (row['ad_soyad'], row['rol'], int(row['aktif_mi']), row['id']))
        baglanti.commit()
        baglanti.close()
        st.success("Kaydedildi!")

elif menu == "📅 Yeni Vardiya Üret":
    st.title("📅 Vardiya Planlama")
    secilen_tarih = st.date_input("Haftanın İlk Günü", value=datetime.now())
    hafta_num = secilen_tarih.isocalendar()[1]

    if st.button("🚀 ÜRET"):
        baglanti = sqlite3.connect('vardiya_sistemi.db')
        cur = baglanti.cursor()
        cur.execute("SELECT id, ad_soyad, rol FROM Personeller WHERE aktif_mi = 1")
        pompacilar, marketciler, p_sozluk = [], [], {}
        for pid, ad, rol in cur.fetchall():
            p_sozluk[pid] = {'ad': ad, 'rol': rol}
            if rol == 'Pompacı': pompacilar.append(pid)
            else: marketciler.append(pid)

        # İzinleri Çek (set olarak - hızlı arama için)
        izin_listesi = cur.execute("SELECT personel_id, tarih FROM Izinler").fetchall()
        izin_set = {(row[0], row[1]) for row in izin_listesi}

        cur.execute("SELECT DISTINCT personel_id FROM VardiyaKayitlari WHERE hafta_numarasi = ? AND vardiya_tipi = 'Gece'", (hafta_num - 1,))
        gececiler = [row[0] for row in cur.fetchall()]
        baglanti.close()

        tum = pompacilar + marketciler
        k_gece_market = get_kural("gece_market_zorunlu")
        k_gece_kisit = get_kural("gecen_hafta_gece_kisiti")
        k_mkt_haftasonu = get_kural("market_haftasonu_calisir")

        # --- Kapasite ön-kontrolü: gerçek personel yetersizliğini kullanıcıya açıkla ---
        market_gece_ihtiyaci = 1 if k_gece_market else 0
        gunluk_pompa_ihtiyaci = 2 + 2 + 2  # gece + sabah + akşam
        gunluk_market_ihtiyaci = market_gece_ihtiyaci + 1 + 1  # gece(opsiyonel) + sabah + akşam
        min_pompaci = -(-(gunluk_pompa_ihtiyaci * 7) // 6)   # ceil(42/6)=7
        min_market = -(-(gunluk_market_ihtiyaci * 7) // 6)   # ceil(14/6)=3 ya da ceil(21/6)=4

        uyarilar = []
        if len(pompacilar) < min_pompaci:
            uyarilar.append(f"En az **{min_pompaci}** Pompacı gerekiyor, mevcut: {len(pompacilar)}.")
        if len(marketciler) < min_market:
            uyarilar.append(f"En az **{min_market}** Market çalışanı gerekiyor, mevcut: {len(marketciler)}.")
        for w in uyarilar:
            st.warning(w)

        # Günlük tarih string'lerini önceden hesapla
        gun_tarihleri = [(secilen_tarih + timedelta(days=g)).strftime('%Y-%m-%d') for g in range(7)]

        model = cp_model.CpModel()
        mesailer = {}
        for p in tum:
            for g in range(7):
                tarih_str = gun_tarihleri[g]
                for v in range(3):
                    mesailer[(p, g, v)] = model.NewBoolVar(f'm_{p}_{g}_{v}')
                    # İzinli günü ise çalışamaz
                    if (p, tarih_str) in izin_set:
                        model.Add(mesailer[(p, g, v)] == 0)

        for p in tum:
            # İzinli gün sayısı kadar haftalık hedef vardiya sayısını düşür.
            # (Eski kod izinli olsa da olmasa da herkesin tam 6 vardiya çalışmasını
            #  zorunlu kılıyordu; 2+ izin günü olan biri için bu imkansızdı.)
            izinli_gun_sayisi = sum(1 for tarih_str in gun_tarihleri if (p, tarih_str) in izin_set)
            hedef_vardiya = max(0, 6 - izinli_gun_sayisi)
            model.Add(sum(mesailer[(p, g, v)] for g in range(7) for v in range(3)) == hedef_vardiya)
            for g in range(7):
                model.Add(sum(mesailer[(p, g, v)] for v in range(3)) <= 1)

        for g in range(7):
            model.Add(sum(mesailer[(p, g, 0)] for p in pompacilar) >= 2)
            if k_gece_market: model.Add(sum(mesailer[(m, g, 0)] for m in marketciler) >= 1)
            for v in [1, 2]:
                model.Add(sum(mesailer[(m, g, v)] for m in marketciler) >= 1)
                model.Add(sum(mesailer[(p, g, v)] for p in pompacilar) >= 2)

        if k_mkt_haftasonu:
            for m in marketciler:
                for g in [5, 6]:
                    tarih_str = gun_tarihleri[g]
                    # İzinliyse bu kişiye "tam 1 çalış" zorunluluğu koyma
                    # (Eski kod bunu izinden bağımsız == 1 yapıyordu, bu da
                    #  izinli+hafta sonu çakışmasında modeli imkansız kılıyordu.)
                    if (m, tarih_str) not in izin_set:
                        model.Add(sum(mesailer[(m, g, v)] for v in range(3)) == 1)

        if k_gece_kisit:
            for p in gececiler:
                if p in tum:
                    for g in range(7): model.Add(mesailer[(p, g, 0)] == 0)

        solver = cp_model.CpSolver()
        durum = solver.Solve(model)
        if durum in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            html = "<table class='shift-table'><tr><th>Gün</th><th>Gece</th><th>Sabah</th><th>Akşam</th><th>İzinliler</th></tr>"
            kayitlar = []
            for g in range(7):
                tarih = secilen_tarih + timedelta(days=g)
                html += f"<tr><td>{tarih.strftime('%d %b')}</td>"
                gunluk_calisanlar = []
                for v in range(3):
                    html += "<td>"
                    for p in tum:
                        if solver.Value(mesailer[(p, g, v)]):
                            cls = "pompa" if p in pompacilar else "market"
                            html += f"<span class='{cls}'>{p_sozluk[p]['ad'].split()[0]}</span><br>"
                            gunluk_calisanlar.append(p)
                            kayitlar.append((p, tarih.strftime('%Y-%m-%d'), hafta_num, ['Gece', 'Sabah', 'Akşam'][v]))
                    html += "</td>"
                html += "<td>"
                for p in tum:
                    if p not in gunluk_calisanlar: html += f"<span class='izinli'>{p_sozluk[p]['ad'].split()[0]}</span><br>"
                html += "</td></tr>"
            st.markdown(html + "</table>", unsafe_allow_html=True)

            conn = sqlite3.connect('vardiya_sistemi.db')
            conn.execute("DELETE FROM VardiyaKayitlari WHERE hafta_numarasi=?", (hafta_num,))
            conn.executemany("INSERT INTO VardiyaKayitlari (personel_id, tarih, hafta_numarasi, vardiya_tipi) VALUES (?,?,?,?)", kayitlar)
            conn.commit()
            conn.close()
        else:
            st.error("Kapasite yetersiz! Lütfen Kural Ayarları'ndan kısıtları gevşetmeyi dene veya personel/izin sayısını kontrol et.")
