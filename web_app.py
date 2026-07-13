import streamlit as st
import sqlite3
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Vardiya Sistemi", page_icon="⛽", layout="wide")

# --- Türkçe Tarih Fonksiyonları ---
aylar_tr = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
gunler_tr = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

def tarih_yaziya_cevir(tarih_obj):
    return f"{tarih_obj.day} {aylar_tr[tarih_obj.month]} {gunler_tr[tarih_obj.weekday()]}"

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
menu = st.sidebar.radio("Menü", ["📅 Yeni Vardiya Üret", "🗂️ Geçmiş Vardiyalar", "👥 Personel Listesi"])

if menu == "👥 Personel Listesi":
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

elif menu == "🗂️ Geçmiş Vardiyalar":
    st.title("🗂️ Geçmiş Vardiyalar (Aylık Görünüm)")
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
        # Tabloyu okunaklı hale getirmek için pivot yapıyoruz
        pivot_df = df_secilen.pivot_table(index='Tarih', columns='Vardiya', values='Personel', aggfunc=lambda x: ', '.join(x)).reset_index()
        st.table(pivot_df)

elif menu == "📅 Yeni Vardiya Üret":
    st.title("📅 Haftalık Vardiya Planlama")
    
    # Tarih Seçici (Pazartesi gününü referans alır)
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
            
            # Kuralların Atanması (Değişkene atayarak Streamlit "None" bug'ını önlüyoruz)
            for p in tum:
                for g in range(7):
                    _ = model.Add(sum(mesailer[(p, g, v)] for v in range(3)) <= 1)
                if p in pompacilar:
                    _ = model.Add(sum(mesailer[(p, g, v)] for g in range(7) for v in range(3)) == 6)
                else:
                    _ = model.Add(sum(mesailer[(p, g, v)] for g in range(7) for v in range(3)) == 5)
            
            for g in range(7):
                _ = model.Add(sum(mesailer[(p, g, 0)] for p in pompacilar) == 1)
                _ = model.Add(sum(mesailer[(m, g, 0)] for m in marketciler) == 0)
                for v in [1, 2]:
                    _ = model.Add(sum(mesailer[(p, g, v)] for p in pompacilar) >= 2)
                    if g < 5: _ = model.Add(sum(mesailer[(m, g, v)] for m in marketciler) >= 1)
            
            for m in marketciler:
                for g in [5, 6]:
                    for v in range(3): _ = model.Add(mesailer[(m, g, v)] == 0)
            
            for p in gececiler:
                if p in tum:
                    for g in range(7): _ = model.Add(mesailer[(p, g, 0)] == 0)
            
            solver = cp_model.CpSolver()
            status = solver.Solve(model)
            
            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                st.success(f"{hafta_num}. Hafta vardiyası başarıyla oluşturuldu ve veritabanına kaydedildi!")
                
                # Çıktı ve Veritabanı Kayıt Aşaması
                tablo_verisi = []
                kayit_listesi = []
                
                for g in range(7):
                    # Tam tarihi hesaplama (Örn: 13 Temmuz Pazartesi)
                    guncel_tarih = secilen_tarih + timedelta(days=g)
                    tarih_metni = tarih_yaziya_cevir(guncel_tarih)
                    tarih_db_formati = guncel_tarih.strftime('%Y-%m-%d')
                    
                    satir = {"Tarih ve Gün": tarih_metni}
                    calisan_idleri = []
                    
                    for v_idx, v_isim in enumerate(['Gece (00-08)', 'Sabah (08-16)', 'Akşam (16-00)']):
                        isimler = []
                        for p in tum:
                            if solver.Value(mesailer[(p, g, v_idx)]) == 1:
                                isim = p_sozluk[p]['ad'].split()[0] # Sadece ilk isim
                                if v_idx == 0 and p in pompacilar: isim += " (M+P)"
                                isimler.append(isim)
                                calisan_idleri.append(p)
                                kayit_listesi.append((p, tarih_db_formati, hafta_num, v_isim.split(' ')[0]))
                                
                        satir[v_isim] = ", ".join(isimler)
                    
                    # İzinlileri Hesaplama
                    izinli_isimleri = []
                    for p in tum:
                        if p not in calisan_idleri:
                            izinli_isimleri.append(p_sozluk[p]['ad'].split()[0])
                    satir["İzinliler"] = ", ".join(izinli_isimleri)
                    
                    tablo_verisi.append(satir)
                
                # Sonuçları veritabanına kaydet (Eski kayıt varsa ezmemek için önce temizler)
                baglanti = sqlite3.connect('vardiya_sistemi.db')
                baglanti.execute("DELETE FROM VardiyaKayitlari WHERE hafta_numarasi = ?", (hafta_num,))
                baglanti.executemany("INSERT INTO VardiyaKayitlari (personel_id, tarih, hafta_numarasi, vardiya_tipi) VALUES (?, ?, ?, ?)", kayit_listesi)
                baglanti.commit()
                baglanti.close()
                
                # Tabloyu ekrana tam genişlikte bas
                df_sonuc = pd.DataFrame(tablo_verisi)
                st.table(df_sonuc)
            else:
                st.error("Mevcut kurallar ve izinlerle uygun bir dağılım bulunamadı!")
