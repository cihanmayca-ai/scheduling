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

GUN_ISIMLERI = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']

# --- Veritabanı ---
def veritabanini_hazirla():
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    cursor = baglanti.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS Personeller (id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT, rol TEXT, aktif_mi INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS VardiyaKayitlari (id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER, tarih TEXT, hafta_numarasi INTEGER, vardiya_tipi TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS Ayarlar (kural_key TEXT PRIMARY KEY, aktif_mi INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS Izinler (id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER, tarih TEXT)''')

    # Varsayılan Kurallar (0/1 anahtar-kapalı kurallar + min personel sayıları)
    varsayilanlar = [
        ("gece_market_zorunlu", 0),
        ("gecen_hafta_gece_kisiti", 1),
        ("market_haftasonu_calisir", 1),
        ("sabit_vardiya_tipi", 0),    # personel aynı hafta içinde hep aynı vardiya tipinde mi çalışsın
        ("min_pompaci_gece", 2),      # gece vardiyasında en az kaç pompacı
        ("min_pompaci_gunduz", 2),    # sabah/akşam vardiyasında en az kaç pompacı
        ("min_market_gunduz", 1),     # sabah/akşam vardiyasında en az kaç market
    ]
    for k, v in varsayilanlar: cursor.execute("INSERT OR IGNORE INTO Ayarlar VALUES (?, ?)", (k, v))
    baglanti.commit()
    baglanti.close()

veritabanini_hazirla()

def get_kural(kural_key):
    """Açık/kapalı (0/1) kurallar için boolean döner."""
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    val = baglanti.execute("SELECT aktif_mi FROM Ayarlar WHERE kural_key=?", (kural_key,)).fetchone()[0]
    baglanti.close()
    return val == 1

def get_deger(kural_key):
    """Min personel sayısı gibi tam sayı değer döndüren ayarlar için."""
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    val = baglanti.execute("SELECT aktif_mi FROM Ayarlar WHERE kural_key=?", (kural_key,)).fetchone()[0]
    baglanti.close()
    return int(val)

def set_deger(kural_key, deger):
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    baglanti.execute("UPDATE Ayarlar SET aktif_mi=? WHERE kural_key=?", (int(deger), kural_key))
    baglanti.commit()
    baglanti.close()

# --- Arayüz ---
st.sidebar.title("⛽ Benzinlik Yönetimi")
menu = st.sidebar.radio("Menü", ["📅 Yeni Vardiya Üret", "🧑‍💼 Vardiyalarım", "🏖️ İzin Planlama", "⚙️ Kural Ayarları", "🗂️ Geçmiş Vardiyalar", "👥 Personel Listesi"])

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

elif menu == "🧑‍💼 Vardiyalarım":
    st.title("🧑‍💼 Kendi Vardiyalarım")
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    personeller = pd.read_sql_query("SELECT id, ad_soyad FROM Personeller WHERE aktif_mi=1", baglanti)

    if personeller.empty:
        st.info("Henüz personel eklenmemiş.")
        baglanti.close()
    else:
        p_sec = st.selectbox("Kendi adınızı seçin:", personeller['ad_soyad'].tolist())
        p_id = int(personeller[personeller['ad_soyad'] == p_sec]['id'].values[0])

        vardiyalar = pd.read_sql_query(
            "SELECT tarih, hafta_numarasi, vardiya_tipi FROM VardiyaKayitlari WHERE personel_id=? ORDER BY tarih",
            baglanti, params=(p_id,)
        )
        izinler = pd.read_sql_query(
            "SELECT tarih FROM Izinler WHERE personel_id=? ORDER BY tarih",
            baglanti, params=(p_id,)
        )
        baglanti.close()

        if vardiyalar.empty:
            st.info(f"{p_sec} için henüz kayıtlı bir vardiya bulunmuyor.")
        else:
            vardiyalar['tarih_dt'] = pd.to_datetime(vardiyalar['tarih'])
            vardiyalar['Gün'] = vardiyalar['tarih_dt'].dt.weekday.map(lambda i: GUN_ISIMLERI[i])
            vardiyalar['Tarih'] = vardiyalar['tarih_dt'].dt.strftime('%d %B %Y')

            for hafta, grup in vardiyalar.sort_values('tarih_dt').groupby('hafta_numarasi', sort=False):
                ilk_gun = grup['tarih_dt'].min().strftime('%d %b')
                son_gun = grup['tarih_dt'].max().strftime('%d %b')
                st.markdown(f"#### 🗓️ Hafta {hafta} ({ilk_gun} - {son_gun})")
                gosterim = grup[['Tarih', 'Gün', 'vardiya_tipi']].rename(columns={'vardiya_tipi': 'Vardiya'})
                st.dataframe(gosterim, use_container_width=True, hide_index=True)

        if not izinler.empty:
            st.markdown("#### 🏖️ İzin Günleriniz")
            st.dataframe(izinler.rename(columns={'tarih': 'Tarih'}), use_container_width=True, hide_index=True)
        else:
            st.caption("Kayıtlı izin gününüz bulunmuyor.")

elif menu == "🗂️ Geçmiş Vardiyalar":
    st.title("🗂️ Geçmiş Vardiyalar")
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    haftalar = pd.read_sql_query(
        "SELECT DISTINCT hafta_numarasi FROM VardiyaKayitlari ORDER BY hafta_numarasi DESC", baglanti
    )

    if haftalar.empty:
        st.info("Henüz oluşturulmuş bir vardiya kaydı yok. Önce '📅 Yeni Vardiya Üret' sayfasından bir vardiya üretmelisin.")
        baglanti.close()
    else:
        hafta_sec = st.selectbox("Hafta Seç:", haftalar['hafta_numarasi'].tolist())
        kayitlar = pd.read_sql_query(
            "SELECT v.tarih, v.vardiya_tipi, p.ad_soyad, p.rol FROM VardiyaKayitlari v "
            "JOIN Personeller p ON v.personel_id = p.id WHERE v.hafta_numarasi=? ORDER BY v.tarih",
            baglanti, params=(int(hafta_sec),)
        )
        baglanti.close()

        if kayitlar.empty:
            st.info("Bu hafta için kayıt bulunamadı.")
        else:
            kayitlar['tarih_dt'] = pd.to_datetime(kayitlar['tarih'])
            gunler = sorted(kayitlar['tarih_dt'].unique())
            ilk_gun, son_gun = pd.Timestamp(gunler[0]), pd.Timestamp(gunler[-1])
            st.caption(f"🗓️ {ilk_gun.strftime('%d %B %Y')} (Pazartesi) → {son_gun.strftime('%d %B %Y')} (Pazar)")

            html = "<table class='shift-table'><tr><th>Gün</th><th>Gece</th><th>Sabah</th><th>Akşam</th></tr>"
            for g in gunler:
                g_ts = pd.Timestamp(g)
                gun_adi = GUN_ISIMLERI[g_ts.weekday()]
                html += f"<tr><td><b>{gun_adi}</b><br>{g_ts.strftime('%d %b')}</td>"
                for v_tipi in ['Gece', 'Sabah', 'Akşam']:
                    html += "<td>"
                    gunluk = kayitlar[(kayitlar['tarih_dt'] == g_ts) & (kayitlar['vardiya_tipi'] == v_tipi)]
                    for _, row in gunluk.iterrows():
                        cls = "pompa" if row['rol'] == 'Pompacı' else "market"
                        html += f"<span class='{cls}'>{row['ad_soyad'].split()[0]}</span><br>"
                    html += "</td>"
                html += "</tr>"
            html += "</table>"
            st.markdown(html, unsafe_allow_html=True)

elif menu == "⚙️ Kural Ayarları":
    st.title("⚙️ Kural Ayarları")
    kural_map = {"gece_market_zorunlu": "Gece vardiyasında mutlaka 1 Market çalışanı olsun", "gecen_hafta_gece_kisiti": "Geçen hafta gece çalışan bu hafta gece çalışamasın", "market_haftasonu_calisir": "Market çalışanları hafta sonu da çalışsın", "sabit_vardiya_tipi": "Personel, hafta içinde hep aynı vardiya tipinde çalışsın (Gece/Sabah/Akşam karışmasın)"}
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    for key, label in kural_map.items():
        durum = get_kural(key)
        if st.toggle(label, value=durum): baglanti.execute("UPDATE Ayarlar SET aktif_mi=1 WHERE kural_key=?", (key,))
        else: baglanti.execute("UPDATE Ayarlar SET aktif_mi=0 WHERE kural_key=?", (key,))
    baglanti.commit()
    baglanti.close()

    st.markdown("---")
    st.markdown("### 👷 Minimum Personel Sayıları")
    st.caption("Personel sayınız yeterli değilse vardiya üretimi 'Kapasite yetersiz' hatası verir. Buradan gerçek personel sayınıza göre ayarlayın.")

    min_pompaci_gece = st.number_input("Gece vardiyasında en az kaç Pompacı?", min_value=0, max_value=10, value=get_deger("min_pompaci_gece"))
    min_pompaci_gunduz = st.number_input("Sabah/Akşam vardiyasında en az kaç Pompacı?", min_value=0, max_value=10, value=get_deger("min_pompaci_gunduz"))
    min_market_gunduz = st.number_input("Sabah/Akşam vardiyasında en az kaç Market çalışanı?", min_value=0, max_value=10, value=get_deger("min_market_gunduz"))

    if st.button("Min Personel Ayarlarını Kaydet"):
        set_deger("min_pompaci_gece", min_pompaci_gece)
        set_deger("min_pompaci_gunduz", min_pompaci_gunduz)
        set_deger("min_market_gunduz", min_market_gunduz)
        st.success("Kaydedildi!")

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
    secilen_tarih = st.date_input("Bir tarih seç (o tarihin içinde bulunduğu Pazartesi-Pazar haftası üretilir)", value=datetime.now())

    # Seçilen tarih hangi gün olursa olsun, her zaman o haftanın Pazartesi'sinden başlat
    pazartesi = secilen_tarih - timedelta(days=secilen_tarih.weekday())
    pazar = pazartesi + timedelta(days=6)
    hafta_num = pazartesi.isocalendar()[1]

    st.caption(f"🗓️ Üretilecek hafta: **{pazartesi.strftime('%d %B %Y')} (Pazartesi) → {pazar.strftime('%d %B %Y')} (Pazar)** — Hafta {hafta_num}")

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
        k_sabit_vardiya = get_kural("sabit_vardiya_tipi")

        # Ayarlanabilir minimum personel sayıları (Kural Ayarları sayfasından değiştirilebilir)
        min_pompaci_gece = get_deger("min_pompaci_gece")
        min_pompaci_gunduz = get_deger("min_pompaci_gunduz")
        min_market_gunduz = get_deger("min_market_gunduz")

        # --- Kapasite ön-kontrolü: gerçek personel yetersizliğini kullanıcıya açıkla ---
        market_gece_ihtiyaci = 1 if k_gece_market else 0
        gunluk_pompa_ihtiyaci = min_pompaci_gece + (min_pompaci_gunduz * 2)  # gece + sabah + akşam
        gunluk_market_ihtiyaci = market_gece_ihtiyaci + (min_market_gunduz * 2)  # gece(opsiyonel) + sabah + akşam
        gereken_pompaci = -(-(gunluk_pompa_ihtiyaci * 7) // 6)   # ceil
        gereken_market = -(-(gunluk_market_ihtiyaci * 7) // 6)   # ceil

        uyarilar = []
        if len(pompacilar) < gereken_pompaci:
            uyarilar.append(f"En az **{gereken_pompaci}** Pompacı gerekiyor, mevcut: {len(pompacilar)}. (Kural Ayarları'ndan min. sayıları düşürebilirsin.)")
        if len(marketciler) < gereken_market:
            uyarilar.append(f"En az **{gereken_market}** Market çalışanı gerekiyor, mevcut: {len(marketciler)}. (Kural Ayarları'ndan min. sayıları düşürebilirsin.)")
        for w in uyarilar:
            st.warning(w)

        # Günlük tarih string'lerini önceden hesapla (Pazartesi'den Pazar'a, g=0 -> Pazartesi, g=6 -> Pazar)
        gun_tarihleri = [(pazartesi + timedelta(days=g)).strftime('%Y-%m-%d') for g in range(7)]

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
            model.Add(sum(mesailer[(p, g, 0)] for p in pompacilar) >= min_pompaci_gece)
            if k_gece_market: model.Add(sum(mesailer[(m, g, 0)] for m in marketciler) >= 1)
            for v in [1, 2]:
                model.Add(sum(mesailer[(m, g, v)] for m in marketciler) >= min_market_gunduz)
                model.Add(sum(mesailer[(p, g, v)] for p in pompacilar) >= min_pompaci_gunduz)

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

        if k_sabit_vardiya:
            # Her personel, o hafta çalıştığı günlerde HEP aynı vardiya tipinde (Gece/Sabah/Akşam) olsun.
            # 3 vardiya tipinden en fazla 1 tanesi "bu hafta bu kişi tarafından kullanıldı" olabilir.
            for p in tum:
                tip_kullanildi = []
                for v in range(3):
                    var = model.NewBoolVar(f'tip_kullan_{p}_{v}')
                    gunluk_degiskenler = [mesailer[(p, g, v)] for g in range(7)]
                    model.Add(sum(gunluk_degiskenler) >= 1).OnlyEnforceIf(var)
                    model.Add(sum(gunluk_degiskenler) == 0).OnlyEnforceIf(var.Not())
                    tip_kullanildi.append(var)
                model.Add(sum(tip_kullanildi) <= 1)

        solver = cp_model.CpSolver()
        durum = solver.Solve(model)
        if durum in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            html = "<table class='shift-table'><tr><th>Gün</th><th>Gece</th><th>Sabah</th><th>Akşam</th><th>İzinliler</th></tr>"
            kayitlar = []
            for g in range(7):
                tarih = pazartesi + timedelta(days=g)
                html += f"<tr><td><b>{GUN_ISIMLERI[g]}</b><br>{tarih.strftime('%d %b')}</td>"
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
