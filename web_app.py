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
    .izinli { opacity: 0.45; text-decoration: line-through; font-size: 12px; }
    .rol-tag { font-size: 10px; padding: 1px 5px; border-radius: 3px; margin-left: 6px; font-weight: normal; }
    .rol-tag-pompa { background: rgba(52, 152, 219, 0.2); color: #3498db; }
    .rol-tag-market { background: rgba(230, 126, 34, 0.2); color: #e67e22; }
    .izin-hucre { text-align: center; font-size: 11px; font-weight: bold; }
    .izin-hucre.pompa { background: rgba(52, 152, 219, 0.15); }
    .izin-hucre.market { background: rgba(230, 126, 34, 0.15); }
    .legend-box { padding: 8px 12px; background: #262626; border-radius: 6px; display: inline-block; margin-bottom: 10px; }
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

    # Varsayılan Kurallar (0/1 anahtar-kapalı kurallar + min personel sayıları)
    varsayilanlar = [
        ("gece_market_zorunlu", 0),
        ("gecen_hafta_gece_kisiti", 1),
        ("market_haftasonu_calisir", 1),
        ("min_pompaci_gece", 2),      # gece vardiyasında en az kaç pompacı (market biri kapsıyorsa 1 azalır)
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
menu = st.sidebar.radio("Menü", ["📅 Yeni Vardiya Üret", "🏖️ İzin Planlama", "⚙️ Kural Ayarları", "🗂️ Geçmiş Vardiyalar", "👥 Personel Listesi"])

if menu == "🏖️ İzin Planlama":
    st.title("🏖️ İzin Planlama")
    baglanti = sqlite3.connect('vardiya_sistemi.db')
    personeller = pd.read_sql_query("SELECT id, ad_soyad, rol FROM Personeller WHERE aktif_mi=1", baglanti)

    with st.form("izin_form"):
        p_sec = st.selectbox("Personel Seç:", personeller['ad_soyad'].tolist())
        tarih_sec = st.date_input("İzin Günü:")
        if st.form_submit_button("İzinli İşaretle"):
            p_id = personeller[personeller['ad_soyad'] == p_sec]['id'].values[0]
            baglanti.execute("INSERT INTO Izinler (personel_id, tarih) VALUES (?, ?)", (int(p_id), tarih_sec.strftime('%Y-%m-%d')))
            baglanti.commit()
            st.success(f"{p_sec} için {tarih_sec} tarihi izinli olarak kaydedildi.")

    st.markdown("---")
    st.markdown("### 📅 Haftalık İzin Takvimi")
    st.markdown(
        "<div class='legend-box'>🔵 <span class='pompa'>Pompacı</span> &nbsp;&nbsp; "
        "🟠 <span class='market'>Market</span> &nbsp;&nbsp; "
        "🔲 Boyalı hücre = İzinli</div>",
        unsafe_allow_html=True
    )

    hafta_baslangic = st.date_input("Takvimde gösterilecek haftanın ilk günü:", value=datetime.now(), key="izin_takvim_hafta")
    gun_tarihleri_izin = [(hafta_baslangic + timedelta(days=g)) for g in range(7)]

    izin_kayitlari = pd.read_sql_query("SELECT personel_id, tarih FROM Izinler", baglanti)
    izin_set_ui = set(zip(izin_kayitlari['personel_id'], izin_kayitlari['tarih']))

    izin_html = "<table class='shift-table'><tr><th>Personel</th>"
    for g in gun_tarihleri_izin:
        izin_html += f"<th>{g.strftime('%d %b')}</th>"
    izin_html += "</tr>"

    # Pompacılar ve marketçiler ayrı bloklar halinde listelensin (roller karışmasın)
    for rol_adi, rol_class in [("Pompacı", "pompa"), ("Market", "market")]:
        alt_grup = personeller[personeller['rol'] == rol_adi]
        if alt_grup.empty:
            continue
        for _, row in alt_grup.iterrows():
            izin_html += f"<tr><td><span class='{rol_class}'>{row['ad_soyad']}</span> <span class='rol-tag rol-tag-{rol_class}'>{row['rol']}</span></td>"
            for g in gun_tarihleri_izin:
                tarih_str = g.strftime('%Y-%m-%d')
                if (row['id'], tarih_str) in izin_set_ui:
                    izin_html += f"<td class='izin-hucre {rol_class}'>İZİNLİ</td>"
                else:
                    izin_html += "<td></td>"
            izin_html += "</tr>"
    izin_html += "</table>"
    st.markdown(izin_html, unsafe_allow_html=True)

    st.markdown("### Kayıtlı Tüm İzinler")
    izinler = pd.read_sql_query("SELECT p.ad_soyad, p.rol, i.tarih FROM Izinler i JOIN Personeller p ON i.personel_id = p.id ORDER BY i.tarih", baglanti)
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

    st.markdown("---")
    st.markdown("### 👷 Minimum Personel Sayıları")
    st.caption("Personel sayınız yeterli değilse vardiya üretimi 'Kapasite yetersiz' hatası verir. Buradan gerçek personel sayınıza göre ayarlayın.")
    st.caption("ℹ️ Gece vardiyasında bir Market çalışanı varsa, o gece için gereken Pompacı sayısı otomatik olarak 1 azalır (toplam gece kapsamı yine bu sayıya ulaşmış olur).")

    min_pompaci_gece = st.number_input("Gece vardiyasında en az kaç Pompacı? (Market biri varsa 1 eksiği yeterli)", min_value=0, max_value=10, value=get_deger("min_pompaci_gece"))
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

        # Ayarlanabilir minimum personel sayıları (Kural Ayarları sayfasından değiştirilebilir)
        min_pompaci_gece = get_deger("min_pompaci_gece")
        min_pompaci_gunduz = get_deger("min_pompaci_gunduz")
        min_market_gunduz = get_deger("min_market_gunduz")

        # --- Kapasite ön-kontrolü: gerçek personel yetersizliğini kullanıcıya açıkla ---
        # Not: Gece'de market biri sayılabildiği için bu sadece yaklaşık bir uyarıdır.
        market_gece_ihtiyaci = 1 if k_gece_market else 0
        gunluk_pompa_ihtiyaci = min_pompaci_gece + (min_pompaci_gunduz * 2)  # gece + sabah + akşam
        gunluk_market_ihtiyaci = market_gece_ihtiyaci + (min_market_gunduz * 2)  # gece(opsiyonel) + sabah + akşam
        gereken_pompaci = -(-(gunluk_pompa_ihtiyaci * 7) // 6)   # ceil
        gereken_market = -(-(gunluk_market_ihtiyaci * 7) // 6)   # ceil

        uyarilar = []
        if len(pompacilar) < gereken_pompaci:
            uyarilar.append(f"En az **{gereken_pompaci}** Pompacı gerekiyor, mevcut: {len(pompacilar)}. (Kural Ayarları'ndan min. sayıları düşürebilirsin. Not: gece vardiyasında market biri varsa bu sayı 1 azalabilir.)")
        if len(marketciler) < gereken_market:
            uyarilar.append(f"En az **{gereken_market}** Market çalışanı gerekiyor, mevcut: {len(marketciler)}. (Kural Ayarları'ndan min. sayıları düşürebilirsin.)")
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
            # --- GECE VARDİYASI KURALI ---
            # Gece'de bir Market çalışanı varsa, o çalışan Pompacı eksikliğinin
            # yerine geçebiliyor kabul edilir: toplam gece kapsamı (Pompacı + Market)
            # min_pompaci_gece sayısına ulaşmalı. Yani market biri varsa 1 pompacı
            # yeterli olur, hiç market yoksa yine min_pompaci_gece kadar pompacı gerekir.
            gece_pompa_toplam = sum(mesailer[(p, g, 0)] for p in pompacilar)
            gece_market_toplam = sum(mesailer[(m, g, 0)] for m in marketciler)
            model.Add(gece_pompa_toplam + gece_market_toplam >= min_pompaci_gece)
            # Yakıt pompalama için gece en az 1 Pompacı her zaman bulunsun (personel varsa).
            if pompacilar:
                model.Add(gece_pompa_toplam >= 1)
            if k_gece_market: model.Add(gece_market_toplam >= 1)
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

        solver = cp_model.CpSolver()
        durum = solver.Solve(model)
        if durum in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            st.markdown(
                "<div class='legend-box'>🔵 <span class='pompa'>Pompacı</span> &nbsp;&nbsp; "
                "🟠 <span class='market'>Market</span> &nbsp;&nbsp; "
                "<span class='izinli pompa'>Soluk/üstü çizili</span> = O gün İzinli/Boşta</div>",
                unsafe_allow_html=True
            )
            html = "<table class='shift-table'><tr><th>Gün</th><th>Gece</th><th>Sabah</th><th>Akşam</th><th>İzinliler / Boştakiler</th></tr>"
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
                            rol_kisa = "P" if p in pompacilar else "M"
                            html += f"<span class='{cls}'>{p_sozluk[p]['ad'].split()[0]}</span><span class='rol-tag rol-tag-{cls}'>{rol_kisa}</span><br>"
                            gunluk_calisanlar.append(p)
                            kayitlar.append((p, tarih.strftime('%Y-%m-%d'), hafta_num, ['Gece', 'Sabah', 'Akşam'][v]))
                    html += "</td>"
                html += "<td>"
                for p in tum:
                    if p not in gunluk_calisanlar:
                        cls = "pompa" if p in pompacilar else "market"
                        html += f"<span class='{cls} izinli'>{p_sozluk[p]['ad'].split()[0]}</span><br>"
                html += "</td></tr>"
            st.markdown(html + "</table>", unsafe_allow_html=True)

            conn = sqlite3.connect('vardiya_sistemi.db')
            conn.execute("DELETE FROM VardiyaKayitlari WHERE hafta_numarasi=?", (hafta_num,))
            conn.executemany("INSERT INTO VardiyaKayitlari (personel_id, tarih, hafta_numarasi, vardiya_tipi) VALUES (?,?,?,?)", kayitlar)
            conn.commit()
            conn.close()
        else:
            st.error("Kapasite yetersiz! Lütfen Kural Ayarları'ndan kısıtları gevşetmeyi dene veya personel/izin sayısını kontrol et.")
