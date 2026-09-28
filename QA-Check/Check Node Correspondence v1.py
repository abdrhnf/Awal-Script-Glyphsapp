#MenuTitle: Check Node Correspondence v1
# -*- coding: utf-8 -*-
"""
Check Node Correspondence v1 — deteksi urutan titik yang KEACAK antar master

Indikator compatibility bawaan Glyphs (segitiga merah di Font View) cuma
nangkep JUMLAH node/path yang beda antar master. Itu TIDAK nangkep kasus
yang beneran kejadian di pipeline Node Rationalizer: dua master jumlah
node-nya SAMA, tapi urutan pemasangannya KEACAK -- titik di deket puncak
stem di master Thin ke-pasang sama titik di lokasi yang beda jauh secara
visual di master Black. Glyphs bilang glyph itu "compatible" (jumlah cocok)
padahal hasil interpolasinya di weight tengah jadi bengkak/melengkung aneh,
karena yang salah itu PASANGAN titiknya, bukan jumlahnya.

Cara kerja: buat tiap pasangan node BERSEBELAHAN di satu path, arah dari
node[i] ke node[i+1] harusnya nunjuk ke arah yang kurang lebih sama di
kedua master (satu bagian outline yang sama nggak mungkin balik arah cuma
gara-gara beda weight). Kalau arahnya kebalik, itu sinyal kuat kalau
pemasangan titik di situ keacak.

KETERBATASAN (jujur, biar nggak dipercaya buta):
- Ketahuan lolos di beberapa kasus asli (d, z, T) tapi kelewat di kasus
  lain yang keliatan jelas pas dicek manual (misal "a") -- korespondensi
  yang keacak nggak selalu menyebabkan arah kebalik, kadang cuma geser
  aneh yang arahnya masih "maju".
- Suka false-positive di glyph yang emang banyak sudut tajam natural
  (M, W, dll) -- sudut tajam yang sah juga bisa kebaca sebagai "flip"
  kalau titik masternya sedikit beda posisi relatif.
- Jadi anggap ini alat TRIASE buat mempersempit yang perlu dicek, bukan
  oracle yang pasti benar. Tetep cross-check pake instance weight tengah
  (generate static instance, render, liat mana yang beneran ngawur).

Taruh di ~/Library/Application Support/Glyphs 3/Scripts/ lalu jalanin dari
menu Script, atau paste langsung ke Macro Panel (Window > Macro Panel)
lalu Cmd+Return.

Glyph yang ketangkep bakal diprint di Macro Panel DAN langsung dibukain
Edit tab baru biar bisa langsung lompat ke situ dan benerin pemasangan
titiknya pake tool node Glyphs sendiri (drag buat reorder, klik-kanan >
Make Node First buat muter start point path).
"""

font = Glyphs.font
if font is None:
    Glyphs.showMacroWindow()
    print("Belum ada font yang kebuka.")
else:
    masters = font.masters
    if len(masters) < 2:
        print("Minimal butuh 2 master buat cek korespondensi.")
    else:
        m1, m2 = masters[0], masters[1]
        flagged = []

        for glyph in font.glyphs:
            layer1 = glyph.layers[m1.id]
            layer2 = glyph.layers[m2.id]
            if layer1 is None or layer2 is None:
                continue
            if len(layer1.paths) != len(layer2.paths):
                continue  # udah ketangkep sama indikator segitiga merah Glyphs sendiri

            bad_paths = []
            for pi, (p1, p2) in enumerate(zip(layer1.paths, layer2.paths)):
                n1, n2 = p1.nodes, p2.nodes
                if len(n1) != len(n2) or len(n1) < 3:
                    continue
                n = len(n1)
                flips = 0
                for i in range(n):
                    a1, a2 = n1[i].position, n1[(i + 1) % n].position
                    b1, b2 = n2[i].position, n2[(i + 1) % n].position
                    vA = (a2.x - a1.x, a2.y - a1.y)
                    vB = (b2.x - b1.x, b2.y - b1.y)
                    lA = (vA[0] ** 2 + vA[1] ** 2) ** 0.5
                    lB = (vB[0] ** 2 + vB[1] ** 2) ** 0.5
                    if lA < 1 or lB < 1:
                        continue
                    cos_sim = (vA[0] * vB[0] + vA[1] * vB[1]) / (lA * lB)
                    if cos_sim < 0:
                        flips += 1
                if flips > 0:
                    bad_paths.append((pi, flips))

            if bad_paths:
                flagged.append((glyph.name, bad_paths))

        Glyphs.showMacroWindow()
        print("Ngecek %d glyph (%s / %s)." % (len(font.glyphs), m1.name, m2.name))
        print("%d yang kemungkinan pemasangan titiknya keacak (jumlah cocok, urutan salah):\n" % len(flagged))
        for name, bad_paths in flagged:
            detail = ", ".join("path %d (%d segmen kebalik)" % (pi, flips) for pi, flips in bad_paths)
            print("  %s: %s" % (name, detail))

        if flagged:
            tab_string = "/" + "/".join(name for name, _ in flagged)
            font.newTab(tab_string)
            print("\nEdit tab baru udah kebuka isinya semua glyph yang ketangkep -- pilih node")
            print("deket path yang ketangkep, terus benerin pake tool node Glyphs sendiri")
            print("(drag buat reorder, klik-kanan > Make Node First, atau Path > Other >")
            print("Rotate Start Point).")
        else:
            print("\nGa ada yang ketangkep keacak di glyph yang jumlah path/node-nya cocok.")
