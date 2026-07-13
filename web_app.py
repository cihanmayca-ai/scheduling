import streamlit as st
import sqlite3
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Vardiya Sistemi", page_icon="⛽", layout="wide")

# --- Veritabanı Kurulumu ---
def veritabanini_hazirla():
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    cursor = baglanti.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS Personeller (id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT, rol TEXT, aktif_mi INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS VardiyaKayitlari (id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER, tarih TEXT, hafta_numarasi INTEGER, vardiya_tipi TEXT)''')
    
    cursor.execute("SELECT COUNT(*) FROM Personeller")
    if cursor.fetchone()[0] == 0:
        ornekler = [("Ahmet Yılmaz", "Pompacı"), ("Mehmet Demir", "Pompacı"), ("Can Yıldız", "Pompacı"), ("Ali Kaya", "Pompacı"), ("Veli Çelik", "Pompacı"), ("Hasan Şahin", "Pompacı"), ("Ayşe Öztürk", "Market"), ("Fatma Aydın", "Market"), ("Zeynep Arslan", "Market")]
        cursor.executemany('INSERT INTO Personeller (ad_soyad, rol) VALUES (?, ?)', ornekler)
    baglanti.commit()
    baglanti.close()

veritabanini_hazirla()

# --- Veri Çekme Fonksiyonu ---
def verileri_cek(hafta_num):
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    cursor = baglanti.cursor()
    cursor.execute("SELECT id, ad_soyad, rol FROM Personeller WHERE aktif_mi = 1")
    pompacilar, marketciler, sozluk = [], [], {}
    for pid, ad, rol in cursor.fetchall():
        sozluk[pid] = {'ad': ad, 'rol': rol}
        pompacilar.append(pid) if rol == 'Pompacı' else marketciler.append(pid)
    
    cursor.execute("SELECT DISTINCT personel_id FROM VardiyaKayitlari WHERE hafta_numarasi = ? AND vardiya_tipi = 'Gece'", (hafta_num - 1,))
    gececiler = [row[0] for row in cursor.fetchall()]
    baglanti.close()
    return pompacilar, marketciler, sozluk, pompacilar + marketciler, gececiler

# --- Web Arayüzü (Sol Menü) ---
st.sidebar.title("⛽ Benzinlik Yönetimi")
menu = st.sidebar.radio("Menü", ["Ana Ekran (Vardiya Hazırla)", "Personel Listesi"])

if menu == "Personel Listesi":
    st.title("👥 Personel Yönetimi")
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    df = pd.read_sql_query("SELECT id as ID, ad_soyad as 'Ad Soyad', rol as Rol, aktif_mi as Durum FROM Personeller", baglanti)
    baglanti.close()
    df['Durum'] = df['Durum'].apply(lambda x: "Aktif" if x == 1 else "Pasif")
    st.dataframe(df, use_container_width=True)
    
    st.subheader("Yeni Personel Ekle")
    with st.form("yeni_personel"):
        yeni_ad = st.text_input("Ad Soyad")
        yeni_rol = st.selectbox("Rol", ["Pompacı", "Market"])
        if st.form_submit_button("Kaydet"):
            if len(yeni_ad) > 2:
                baglanti = sqlite3.connect('vardiya_sistemi.db')
                baglanti.execute("INSERT INTO Personeller (ad_soyad, rol) VALUES (?, ?)", (yeni_ad, yeni_rol))
                baglanti.commit()
                baglanti.close()
                st.success("Personel eklendi! Listeyi yenilemek için sayfayı tazeleyin.")

elif menu == "Ana Ekran (Vardiya Hazırla)":
    st.title("📅 Haftalık Vardiya Planlama")
    
    if st.button("🚀 Yeni Hafta Vardiyasını Üret", type="primary"):
        with st.spinner("Yapay zeka kuralları hesaplıyor..."):
            hafta_num = datetime.now().isocalendar()[1]
            pompacilar, marketciler, p_sozluk, tum, gececiler = verileri_cek(hafta_num)
            
            model = cp_model.CpModel()
            mesailer = {}
            for p in tum:
                for g in range(7):
                    for v in range(3):
                        mesailer[(p, g, v)] = model.NewBoolVar(f'm_{p}_{g}_{v}')
            
            # Kurallar
            for p in tum:
                for g in range(7):
                    model.Add(sum(mesailer[(p, g, v)] for v in range(3)) <= 1)
                if p in pompacilar:
                    model.Add(sum(mesailer[(p, g, v)] for g in range(7) for v in range(3)) == 6)
                else:
                    model.Add(sum(mesailer[(p, g, v)] for g in range(7) for v in range(3)) == 5)
            
            for g in range(7):
                model.Add(sum(mesailer[(p, g, 0)] for p in pompacilar) == 1)
                model.Add(sum(mesailer[(m, g, 0)] for m in marketciler) == 0)
                for v in [1, 2]:
                    model.Add(sum(mesailer[(p, g, v)] for p in pompacilar) >= 2)
                    if g < 5: model.Add(sum(mesailer[(m, g, v)] for m in marketciler) >= 1)
            
            for m in marketciler:
                for g in [5, 6]:
                    for v in range(3): model.Add(mesailer[(m, g, v)] == 0)
            
            for p in gececiler:
                if p in tum:
                    for g in range(7): model.Add(mesailer[(p, g, 0)] == 0)
            
            solver = cp_model.CpSolver()
            status = solver.Solve(model)
            
            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                st.success("Vardiya başarıyla oluşturuldu!")
                gunler = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
                tablo_verisi = []
                
                for g in range(7):
                    satir = {"Gün": gunler[g]}
                    for v_idx, v_isim in enumerate(['Gece (00-08)', 'Sabah (08-16)', 'Akşam (16-00)']):
                        isimler = []
                        for p in tum:
                            if solver.Value(mesailer[(p, g, v_idx)]) == 1:
                                isim = p_sozluk[p]['ad'].split()[0]
                                if v_idx == 0 and p in pompacilar: isim += " (M+P)"
                                isimler.append(isim)
                        satir[v_isim] = ", ".join(isimler)
                    tablo_verisi.append(satir)
                
                # Tabloyu Ekrana Bas
                df_sonuc = pd.DataFrame(tablo_verisi)
                st.table(df_sonuc)
            else:
                st.error("Mevcut kısıtlarla uygun bir dağılım bulunamadı!")