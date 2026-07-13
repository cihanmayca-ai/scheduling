import streamlit as st
import sqlite3
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Vardiya Sistemi", page_icon="⛽", layout="wide")

# --- CSS Stilleri ---
st.markdown("""
<style>
    .shift-table { width: 100%; border-collapse: collapse; font-family: sans-serif; background-color: #1E1E1E; }
    .shift-table th, .shift-table td { border: 1px solid #333; padding: 10px; text-align: left; }
    .shift-table th { background-color: #2C3E50; color: white; }
    .pompa { color: #3498db; font-weight: bold; }
    .market { color: #e67e22; font-weight: bold; }
    .izinli { color: #e74c3c; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# --- Veritabanı ve Yardımcılar ---
def veritabanini_hazirla():
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    cursor = baglanti.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS Personeller (id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT, rol TEXT, aktif_mi INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS VardiyaKayitlari (id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER, tarih TEXT, hafta_numarasi INTEGER, vardiya_tipi TEXT)''')
    baglanti.commit()
    baglanti.close()

veritabanini_hazirla()

def verileri_cek(hafta_num):
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    cursor = baglanti.cursor()
    cursor.execute("SELECT id, ad_soyad, rol FROM Personeller WHERE aktif_mi = 1")
    pompacilar, marketciler, sozluk = [], [], {}
    for pid, ad, rol in cursor.fetchall():
        sozluk[pid] = {'ad': ad, 'rol': rol}
        if rol == 'Pompacı': pompacilar.append(pid)
        else: marketciler.append(pid)
    
    # Geçen hafta gece olanlar
    cursor.execute("SELECT DISTINCT personel_id FROM VardiyaKayitlari WHERE hafta_numarasi = ? AND vardiya_tipi = 'Gece'", (hafta_num - 1,))
    gececiler = [row[0] for row in cursor.fetchall()]
    baglanti.close()
    return pompacilar, marketciler, sozluk, pompacilar + marketciler, gececiler

# --- Arayüz ---
st.sidebar.title("⛽ Benzinlik Yönetimi")
menu = st.sidebar.radio("Menü", ["📅 Yeni Vardiya Üret", "🗂️ Geçmiş Vardiyalar", "👥 Personel Listesi"])

if menu == "👥 Personel Listesi":
    st.title("👥 Personel Yönetimi")
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    df = pd.read_sql_query("SELECT id, ad_soyad, rol, aktif_mi FROM Personeller", baglanti)
    baglanti.close()
    
    edited_df = st.data_editor(df, column_config={"id": st.column_config.NumberColumn(disabled=True)}, use_container_width=True)
    
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
        pompacilar, marketciler, p_sozluk, tum, gececiler = verileri_cek(hafta_num)
        model = cp_model.CpModel()
        mesailer = {}
        for p in tum:
            for g in range(7):
                for v in range(3): mesailer[(p, g, v)] = model.NewBoolVar(f'm_{p}_{g}_{v}')
        
        # Herkes haftada 6 gün çalışır
        for p in tum:
            model.Add(sum(mesailer[(p, g, v)] for g in range(7) for v in range(3)) == 6)
            for g in range(7): model.Add(sum(mesailer[(p, g, v)] for v in range(3)) <= 1)

        for g in range(7):
            # Gece (v=0): Sadece 2 Pompacı (Marketçi opsiyonel)
            model.Add(sum(mesailer[(p, g, 0)] for p in pompacilar) >= 2)
            
            # Sabah(v=1) ve Akşam(v=2): En az 1 Market, 2 Pompa
            for v in [1, 2]:
                model.Add(sum(mesailer[(m, g, v)] for m in marketciler) >= 1)
                model.Add(sum(mesailer[(p, g, v)] for p in pompacilar) >= 2)
        
        # Geçen hafta gece olanlar gece çalışamaz
        for p in gececiler:
            if p in tum:
                for g in range(7): model.Add(mesailer[(p, g, 0)] == 0)

        solver = cp_model.CpSolver()
        if solver.Solve(model) == cp_model.OPTIMAL:
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
                            kayitlar.append((p, tarih.strftime('%Y-%m-%d'), hafta_num, ['Gece','Sabah','Akşam'][v]))
                    html += "</td>"
                
                html += "<td>"
                for p in tum:
                    if p not in gunluk_calisanlar: html += f"<span class='izinli'>{p_sozluk[p]['ad'].split()[0]}</span><br>"
                html += "</td></tr>"
            st.markdown(html + "</table>", unsafe_allow_html=True)
            
            # Kaydet
            conn = sqlite3.connect('vardiya_sistemi.db')
            conn.execute("DELETE FROM VardiyaKayitlari WHERE hafta_numarasi=?", (hafta_num,))
            conn.executemany("INSERT INTO VardiyaKayitlari (personel_id, tarih, hafta_numarasi, vardiya_tipi) VALUES (?,?,?,?)", kayitlar)
            conn.commit()
            conn.close()
        else:
            st.error("Kapasite yetersiz! Personel sayınız bu kuralları karşılamıyor.")
