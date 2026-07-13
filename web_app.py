import streamlit as st
import sqlite3
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Vardiya Sistemi", page_icon="⛽", layout="wide")

# --- HTML/CSS Şablonları (Renkli Tablo İçin) ---
st.markdown("""
<style>
    .shift-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-family: sans-serif; }
    .shift-table th, .shift-table td { border: 1px solid #444; padding: 12px; text-align: left; vertical-align: top; }
    .shift-table th { background-color: #2C3E50; color: white; font-size: 16px; }
    .shift-table tr:nth-child(even) { background-color: #1A1A1A; }
    .shift-table tr:nth-child(odd) { background-color: #212121; }
    
    .pompa { color: #3498db; font-weight: bold; background-color: rgba(52, 152, 219, 0.1); padding: 4px 8px; border-radius: 4px; display: inline-block; margin: 2px 0; border: 1px solid #3498db; }
    .market { color: #e67e22; font-weight: bold; background-color: rgba(230, 126, 34, 0.1); padding: 4px 8px; border-radius: 4px; display: inline-block; margin: 2px 0; border: 1px solid #e67e22; }
    .izinli { color: #e74c3c; font-weight: bold; background-color: rgba(231, 76, 60, 0.1); padding: 4px 8px; border-radius: 4px; display: inline-block; margin: 2px; border: 1px dashed #e74c3c; font-size: 13px; }
    .tarih-sutun { font-weight: bold; font-size: 15px; color: #ecf0f1; width: 120px; }
</style>
""", unsafe_allow_html=True)

# --- Türkçe Tarih Fonksiyonları ---
aylar_tr = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
gunler_tr = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

def tarih_yaziya_cevir(tarih_obj):
    return f"{tarih_obj.day} {aylar_tr[tarih_obj.month]}<br><span style='font-size:12px; color:#bdc3c7;'>{gunler_tr[tarih_obj.weekday()]}</span>"

# --- Veritabanı Kurulumu ---
def veritabanini_hazirla():
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    cursor = baglanti.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS Personeller (id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT, rol TEXT, aktif_mi INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS VardiyaKayitlari (id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER, tarih TEXT, hafta_numarasi INTEGER, vardiya_tipi TEXT)''')
    
    cursor.execute("SELECT COUNT(*) FROM Personeller")
    if cursor.fetchone()[0] == 0:
        # Gece kuralı gereği matematiğin tutması için 4 Market personeli eklendi
        ornekler = [
            ("Ahmet Yılmaz", "Pompacı"), ("Mehmet Demir", "Pompacı"), ("Can Yıldız", "Pompacı"), 
            ("Ali Kaya", "Pompacı"), ("Veli Çelik", "Pompacı"), ("Hasan Şahin", "Pompacı"), 
            ("Ayşe Öztürk", "Market"), ("Fatma Aydın", "Market"), ("Zeynep Arslan", "Market"), ("Kemal Güneş", "Market")
        ]
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
menu = st.sidebar.radio("Menü", ["📅 Yeni Vardiya Üret", "🗂️ Geçmiş Vardiyalar", "👥 Personel Listesi"])

if menu == "👥 Personel Listesi":
    st.title("👥 Personel Yönetimi")
    st.info("Tablo üzerinde isimleri ve rolleri doğrudan düzenleyebilirsin. Düzenleme bittikten sonra aşağıdaki 'Değişiklikleri Kaydet' butonuna basmayı unutma.")
    
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    df = pd.read_sql_query("SELECT id, ad_soyad, rol, aktif_mi FROM Personeller", baglanti)
    baglanti.close()
    
    # Interaktif / Düzenlenebilir Tablo
    edited_df = st.data_editor(
        df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "ad_soyad": st.column_config.TextColumn("Ad Soyad"),
            "rol": st.column_config.SelectboxColumn("Rol", options=["Pompacı", "Market"]),
            "aktif_mi": st.column_config.CheckboxColumn("Aktif mi?", default=True)
        },
        use_container_width=True,
        hide_index=True
    )
    
    if st.button("💾 Değişiklikleri Kaydet", type="primary"):
        baglanti = sqlite3.connect('vardiya_sistemi.db')
        cursor = baglanti.cursor()
        for index, row in edited_df.iterrows():
            cursor.execute("UPDATE Personeller SET ad_soyad=?, rol=?, aktif_mi=? WHERE id=?", 
                           (row['ad_soyad'], row['rol'], int(row['aktif_mi']), row['id']))
        baglanti.commit()
        baglanti.close()
        st.success("Personel listesi başarıyla güncellendi!")

    st.markdown("---")
    st.subheader("Yeni Personel Ekle")
    with st.form("yeni_personel"):
        col1, col2 = st.columns(2)
        yeni_ad = col1.text_input("Ad Soyad")
        yeni_rol = col2.selectbox("Rol", ["Pompacı", "Market"])
        if st.form_submit_button("Sisteme Ekle"):
            if len(yeni_ad) > 2:
                baglanti = sqlite3.connect('vardiya_sistemi.db')
                baglanti.execute("INSERT INTO Personeller (ad_soyad, rol) VALUES (?, ?)", (yeni_ad, yeni_rol))
                baglanti.commit()
                baglanti.close()
                st.success("Personel eklendi! Listeyi yenilemek için sayfayı tazeleyin.")

elif menu == "🗂️ Geçmiş Vardiyalar":
    st.title("🗂️ Geçmiş Vardiyalar")
    st.warning("Gelişmiş renkli görünüm 'Yeni Vardiya Üret' ekranındadır. Bu alan ham veri kontrolü içindir.")
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    df_gecmis = pd.read_sql_query('''
        SELECT v.hafta_numarasi as 'Hafta', v.tarih as 'Tarih', p.ad_soyad as 'Personel', p.rol as 'Rol', v.vardiya_tipi as 'Vardiya'
        FROM VardiyaKayitlari v
        JOIN Personeller p ON v.personel_id = p.id
        ORDER BY v.tarih DESC
    ''', baglanti)
    baglanti.close()

    if df_gecmis.empty:
        st.info("Henüz kaydedilmiş bir vardiya bulunmuyor.")
    else:
        haftalar = df_gecmis['Hafta'].unique()
        secilen_hafta = st.selectbox("Görüntülemek İstediğiniz Haftayı Seçin", haftalar)
        df_secilen = df_gecmis[df_gecmis['Hafta'] == secilen_hafta]
        pivot_df = df_secilen.pivot_table(index='Tarih', columns='Vardiya', values='Personel', aggfunc=lambda x: ', '.join(x)).reset_index()
        st.table(pivot_df)

elif menu == "📅 Yeni Vardiya Üret":
    st.title("📅 Haftalık Vardiya Planlama")
    
    bugun = datetime.now()
    gecerli_pazartesi = bugun - timedelta(days=bugun.weekday())
    secilen_tarih = st.date_input("Haftanın İlk Gününü Seçin (Pazartesi)", value=gecerli_pazartesi)
    hafta_num = secilen_tarih.isocalendar()[1]
    
    if st.button("🚀 Seçili Hafta İçin Vardiya Üret", type="primary"):
        with st.spinner("Yapay zeka kuralları hesaplıyor..."):
            pompacilar, marketciler, p_sozluk, tum, gececiler = verileri_cek(hafta_num)
            
            model = cp_model.CpModel()
            mesailer = {}
            for p in tum:
                for g in range(7):
                    for v in range(3):
                        mesailer[(p, g, v)] = model.NewBoolVar(f'm_{p}_{g}_{v}')
            
            # --- KURALLAR ---
            for p in tum:
                for g in range(7):
                    _ = model.Add(sum(mesailer[(p, g, v)] for v in range(3)) <= 1) # Günde 1 vardiya
                if p in pompacilar:
                    _ = model.Add(sum(mesailer[(p, g, v)] for g in range(7) for v in range(3)) == 6) # Pompacı haftada 6 gün
                else:
                    _ = model.Add(sum(mesailer[(p, g, v)] for g in range(7) for v in range(3)) == 6) # Market de 6 gün (Aksi taktirde kapasite yetmez)
            
            for g in range(7):
                # GECE VARDİYASI (En az 1 pompa, 1 market)
                _ = model.Add(sum(mesailer[(p, g, 0)] for p in pompacilar) >= 1)
                _ = model.Add(sum(mesailer[(m, g, 0)] for m in marketciler) >= 1)
                
                # SABAH & AKŞAM VARDİYALARI
                for v in [1, 2]:
                    _ = model.Add(sum(mesailer[(p, g, v)] for p in pompacilar) >= 2)
                    _ = model.Add(sum(mesailer[(m, g, v)] for m in marketciler) >= 1)
            
            # Marketçiler Haftasonu İzin YAPAMAZ (Sadece haftaiçi yaparlar)
            for m in marketciler:
                for g in [5, 6]:
                    _ = model.Add(sum(mesailer[(m, g, v)] for v in range(3)) == 1)
            
            # Geçen hafta gece olan bu hafta gece olamaz
            for p in gececiler:
                if p in tum:
                    for g in range(7): _ = model.Add(mesailer[(p, g, 0)] == 0)
            
            solver = cp_model.CpSolver()
            status = solver.Solve(model)
            
            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                st.success(f"{hafta_num}. Hafta vardiyası başarıyla oluşturuldu!")
                
                kayit_listesi = []
                html_tablo = "<table class='shift-table'><thead><tr><th>Tarih ve Gün</th><th>Gece (00-08)</th><th>Sabah (08-16)</th><th>Akşam (16-00)</th><th>🏖️ İzinliler</th></tr></thead><tbody>"
                
                for g in range(7):
                    guncel_tarih = secilen_tarih + timedelta(days=g)
                    tarih_metni = tarih_yaziya_cevir(guncel_tarih)
                    tarih_db_formati = guncel_tarih.strftime('%Y-%m-%d')
                    
                    html_tablo += f"<tr><td class='tarih-sutun'>{tarih_metni}</td>"
                    calisan_idleri = []
                    
                    for v_idx, v_isim in enumerate(['Gece', 'Sabah', 'Akşam']):
                        html_tablo += "<td>"
                        for p in tum:
                            if solver.Value(mesailer[(p, g, v_idx)]) == 1:
                                isim = p_sozluk[p]['ad'].split()[0]
                                rol = p_sozluk[p]['rol']
                                cls = "pompa" if rol == "Pompacı" else "market"
                                
                                html_tablo += f"<span class='{cls}'>{isim}</span><br>"
                                calisan_idleri.append(p)
                                kayit_listesi.append((p, tarih_db_formati, hafta_num, v_isim))
                        html_tablo += "</td>"
                    
                    # O Gün İzinli Olanları Tespit Et ve Kırmızı Renkle Ekle
                    html_tablo += "<td>"
                    for p in tum:
                        if p not in calisan_idleri:
                            isim = p_sozluk[p]['ad'].split()[0]
                            rol = "P" if p_sozluk[p]['rol'] == "Pompacı" else "M"
                            html_tablo += f"<span class='izinli'>{isim} ({rol})</span>"
                    html_tablo += "</td></tr>"
                
                html_tablo += "</tbody></table>"
                
                # HTML Tabloyu Ekrana Bas
                st.markdown(html_tablo, unsafe_allow_html=True)
                
                # Veritabanına Kaydet
                baglanti = sqlite3.connect('vardiya_sistemi.db')
                baglanti.execute("DELETE FROM VardiyaKayitlari WHERE hafta_numarasi = ?", (hafta_num,))
                baglanti.executemany("INSERT INTO VardiyaKayitlari (personel_id, tarih, hafta_numarasi, vardiya_tipi) VALUES (?, ?, ?, ?)", kayit_listesi)
                baglanti.commit()
                baglanti.close()
                
            else:
                st.error("Mevcut kurallar, kapasite ve izinlerle uygun bir dağılım bulunamadı! Personel sayısının yeterli olduğundan emin olun.")
