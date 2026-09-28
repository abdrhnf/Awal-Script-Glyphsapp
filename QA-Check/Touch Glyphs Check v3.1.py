#MenuTitle: Check Pair Touch v3.1 (true vector + union-area)…
# -*- coding: utf-8 -*-
"""
Check Pair Touch v3.1 — TRUE VECTOR distance + UNION-AREA verification
Perbaikan penting dibanding v1/v2:

1. v1/v2 pakai scanline HORIZONTAL per pita-Y 5 unit. Itu buta terhadap
   jarak VERTIKAL: pair seperti c+Z terbaca "overlap -50" padahal tinta
   TIDAK bersentuhan. v3 memverifikasi setiap pair yang "lolos" scanline
   dengan jarak segmen-ke-segmen 2D pada outline yang sudah di-removeOverlap
   (sliver/ekor konstruksi tidak dihitung sebagai tinta) — false PASS ketahuan.
2. Kerning dibaca group-aware (glyph-glyph > glyph-group > group-glyph >
   group-group), persis cara Glyphs merender. v1 membaca group kerning = 0.
3. Fix pakai binary/step search: cari kerning kontak sesungguhnya (jarak
   vektor = 0) lalu tambah depth. Bukan sekadar geser sebesar gap horizontal
   — penting untuk kasus vertikal seperti c+Z.
4. Setiap fix diverifikasi ulang: kern dibaca kembali dari font, jarak
   dihitung ulang. Pair yang masih gagal dilaporkan di Macro window.

RIWAYAT VERSI:
- v3   : jarak vektor 2D true (segmen-ke-segmen), group-aware kerning,
         fix step+binary search, semua diverifikasi ulang.
- v3.1 : + adaptive curve flattening (FLATTEN_TOL, ganti N sampel tetap --
         lebih presisi & konsisten di kurva tajam/sudut landai) dan
         UNION-AREA CHECK (find_solid_contact_kern/check_area_overlap):
         gabung dua outline + removeOverlap() NATIVE Glyphs.app, verifikasi
         irisan TINTA beneran (bukan cuma jarak vektor) -- penting utk
         pair yang nyentuh di sudut landai (co. c+Z) dimana jarak vektor
         bisa 0 (kurva beneran bersilangan) padahal belum ada tinta yang
         benar-benar menyatu.

Taruh di ~/Library/Application Support/Glyphs 3/Scripts/ lalu Cmd+Opt+Shift+Y.
"""

import os
import re
from datetime import datetime
try:
    import vanilla
    import vanilla.dialogs
except Exception:
    vanilla = None   # supaya core bisa dites headless

REFERENCE_UPM   = 1000.0  # thresholds di bawah ini dikalibrasi di UPM referensi ini
_Y_STEP_BASE          = 5     # resolusi pita scanline (unit, @ REFERENCE_UPM)
_TOUCH_TOL_BASE       = 1.0   # jarak <= ini dianggap nempel (unit, @ REFERENCE_UPM)
_MIN_OVERLAP_AREA_BASE = 300.0  # ambang overlap-area (unit^2, @ REFERENCE_UPM)
MAX_KERN_SHIFT  = 2000  # batas pergeseran fix

# Nilai LIVE (di-rescale oleh _configure_scale_for_font() begitu font.upm
# diketahui, dipanggil di awal run_test). Sengaja module-level (bukan default
# parameter) karena default parameter di-bind SEKALI saat modul di-load --
# reassign global di sini tetap kebaca fresh oleh setiap referensi langsung
# di badan fungsi manapun, jadi satu font dengan UPM non-1000 pun dapat
# threshold yang proporsional, bukan angka yang dikalibrasi utk font lain.
Y_STEP    = _Y_STEP_BASE
TOUCH_TOL = _TOUCH_TOL_BASE
MIN_OVERLAP_AREA = _MIN_OVERLAP_AREA_BASE


def _configure_scale_for_font(font):
    """Rescale Y_STEP/TOUCH_TOL (jarak, skala linear) dan MIN_OVERLAP_AREA
    (luas, skala kuadrat) ke UPM font aktif. Dipanggil sekali di awal
    run_test, SEBELUM data glyph mana pun dibangun."""
    global Y_STEP, TOUCH_TOL, MIN_OVERLAP_AREA
    upm = getattr(font, 'upm', None) or REFERENCE_UPM
    scale = upm / REFERENCE_UPM
    Y_STEP = max(1, int(round(_Y_STEP_BASE * scale)))
    TOUCH_TOL = _TOUCH_TOL_BASE * scale
    MIN_OVERLAP_AREA = _MIN_OVERLAP_AREA_BASE * (scale ** 2)

# --- flatten kurva: ADAPTIF, bukan N tetap ----------------------------------
# RIWAYAT MASALAH: versi lama sampling tiap kurva pakai N titik TETAP
# (SAMPLES_PER_SEG=10, atau 40 utk A-Z/a-z via STRICT_GLYPHS). Terbukti lewat
# pengetesan silang (bandingkan hasil di N=10/40/100/300/1000/2000) bahwa
# pendekatan itu TIDAK KONVERGEN buat pasangan dgn kurva tajam/melengkung
# curam (co. c+Z): jarak yang terhitung goyang liar (0.0 s/d ~1.0) tergantung
# N yang dipakai -- artinya verdict nempel/tidak bisa BEDA cuma krn pilihan
# N, bukan krn geometri sebenarnya beda. N tetap = jumlah titik sama rata di
# sepanjang kurva walau kelengkungannya nggak rata; di tikungan tajam, garis
# lurus antar titik sampel meleset jauh dari kurva asli.
#
# FIX: flatten ADAPTIF (rekursif, ala de Casteljau) -- subdivide kurva terus
# SAMPAI deviasi titik kontrol dari garis lurus (chord) <= FLATTEN_TOL. Kurva
# landai otomatis dapet sedikit titik (murah), kurva/tikungan tajam otomatis
# dapet banyak titik (presisi) -- bukan jumlah titik seragam yang menebak
# resolusi kurva bakal seperti apa. FLATTEN_TOL sengaja jauh LEBIH KECIL dari
# TOUCH_TOL supaya galat aproksimasi kurva tidak pernah jadi sumber noise
# pada keputusan nempel/tidak.
FLATTEN_TOL       = 0.1   # deviasi maksimum kurva->garis lurus yang diizinkan (unit)
FLATTEN_MAX_DEPTH = 12    # batas rekursi (aman, 2^12 titik per segmen kalaupun ekstrem)


# ══════════════════════════════════════════════════════════════════════════════
# OUTLINE SAMPLING (komponen ikut diratakan, transform nested didukung)
# ══════════════════════════════════════════════════════════════════════════════

def _apply_xform(xform, x, y):
    m11, m12, m21, m22, tx, ty = xform
    return m11*x + m21*y + tx, m12*x + m22*y + ty

def _comp_xform(comp):
    try:
        t = comp.transform
        if isinstance(t, (tuple, list)) and len(t) == 6: return tuple(t)
        return (t.m11, t.m12, t.m21, t.m22, t.tX, t.tY)
    except Exception: pass
    try:
        pos = comp.position; return (1,0,0,1,pos.x,pos.y)
    except Exception: return (1,0,0,1,0,0)

def _mul_xform(a, b):
    am11,am12,am21,am22,atx,aty = a
    bm11,bm12,bm21,bm22,btx,bty = b
    return (am11*bm11+am21*bm12, am12*bm11+am22*bm12,
            am11*bm21+am21*bm22, am12*bm21+am22*bm22,
            am11*btx+am21*bty+atx, am12*btx+am22*bty+aty)

def _layer_bbox_fast(layer, xform=(1,0,0,1,0,0)):
    """Bounding box CEPAT (pakai layer.bounds, tanpa sampling penuh),
    ditransform sesuai xform komponen. None kalau gagal (fallback dipakai)."""
    try:
        b = layer.bounds
        x0, y0 = b.origin.x, b.origin.y
        x1, y1 = x0 + b.size.width, y0 + b.size.height
    except Exception:
        return None
    corners = [(x0,y0),(x1,y0),(x0,y1),(x1,y1)]
    txs = [_apply_xform(xform, cx, cy) for cx, cy in corners]
    xs = [p[0] for p in txs]; ys = [p[1] for p in txs]
    return (min(xs), min(ys), max(xs), max(ys))

def _bbox_disjoint(a, b):
    """True HANYA kalau dua bbox benar-benar tidak bersinggungan (strict).
    Kalau salah satu None atau bbox saling sentuh/overlap -> False (aman,
    biar fallback ke removeOverlap penuh yang pasti benar)."""
    if a is None or b is None: return False
    ax0,ay0,ax1,ay1 = a; bx0,by0,bx1,by1 = b
    return ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0

def _mid(a, b):
    return ((a[0]+b[0])*0.5, (a[1]+b[1])*0.5)

def _cubic_flat_enough(p0, p1, p2, p3, tol):
    """True kalau kedua titik kontrol (p1,p2) cukup dekat ke garis lurus
    p0->p3 (deviasi <= tol) -- kalau iya, kurva ini boleh diwakili garis
    lurus tanpa nambah galat berarti."""
    x0, y0 = p0; x3, y3 = p3
    dx = x3 - x0; dy = y3 - y0
    L = (dx*dx + dy*dy) ** 0.5
    if L < 1e-9:
        d1 = ((p1[0]-x0)**2 + (p1[1]-y0)**2) ** 0.5
        d2 = ((p2[0]-x0)**2 + (p2[1]-y0)**2) ** 0.5
        return max(d1, d2) <= tol
    d1 = abs((p1[0]-x0)*dy - (p1[1]-y0)*dx) / L
    d2 = abs((p2[0]-x0)*dy - (p2[1]-y0)*dx) / L
    return d1 <= tol and d2 <= tol

def _flatten_cubic(p0, p1, p2, p3, tol, depth, out):
    """Subdivide kurva kubik (de Casteljau) rekursif SAMPAI flat (deviasi <=
    tol), baru catat titik akhir tiap sub-segmen. Kurva landai -> sedikit
    subdivide (murah). Kurva/tikungan tajam -> otomatis banyak subdivide
    (presisi) -- bukan N tetap yang menebak-nebak kelengkungan."""
    if depth >= FLATTEN_MAX_DEPTH or _cubic_flat_enough(p0, p1, p2, p3, tol):
        out.append(p3); return
    p01 = _mid(p0, p1); p12 = _mid(p1, p2); p23 = _mid(p2, p3)
    p012 = _mid(p01, p12); p123 = _mid(p12, p23)
    p0123 = _mid(p012, p123)
    _flatten_cubic(p0, p01, p012, p0123, tol, depth+1, out)
    _flatten_cubic(p0123, p123, p23, p3, tol, depth+1, out)

def _quad_flat_enough(p0, p1, p2, tol):
    x0, y0 = p0; x2, y2 = p2
    dx = x2 - x0; dy = y2 - y0
    L = (dx*dx + dy*dy) ** 0.5
    if L < 1e-9:
        return (((p1[0]-x0)**2 + (p1[1]-y0)**2) ** 0.5) <= tol
    d = abs((p1[0]-x0)*dy - (p1[1]-y0)*dx) / L
    return d <= tol

def _flatten_quad(p0, p1, p2, tol, depth, out):
    if depth >= FLATTEN_MAX_DEPTH or _quad_flat_enough(p0, p1, p2, tol):
        out.append(p2); return
    p01 = _mid(p0, p1); p12 = _mid(p1, p2)
    p012 = _mid(p01, p12)
    _flatten_quad(p0, p01, p012, tol, depth+1, out)
    _flatten_quad(p012, p12, p2, tol, depth+1, out)

def _sample_path(path, xform=(1,0,0,1,0,0)):
    """Flatten satu path jadi polyline (kurva di-flatten ADAPTIF, lihat
    FLATTEN_TOL). QCURVE dengan LEBIH DARI SATU off-curve node berturut-turut
    (konvensi TrueType: titik on-curve di antaranya IMPLISIT, midpoint dari
    dua off-curve bertetangga) di-expand jadi rantai segmen kuadratik yang
    benar -- bukan diperlakukan sebagai satu segmen dengan satu titik kontrol
    yang salah (off-curve sebelumnya sempat ke-drop diam-diam)."""
    nodes = list(path.nodes)
    if not nodes: return []
    start = 0
    for i, n in enumerate(nodes):
        nt = n.type.upper() if isinstance(n.type, str) else str(n.type).upper()
        if nt in ('LINE','CURVE','QCURVE'): start = i; break
    ordered = nodes[start:] + nodes[:start]
    if path.closed: ordered.append(ordered[0])

    def node_xy(n):
        return _apply_xform(xform, n.position.x, n.position.y)

    pts = []
    prev = ordered[0]
    # titik awal ikut ditambahkan biar segmen pertama (kalau LINE) lengkap
    pts.append(node_xy(prev))
    offcurve_run = []
    i = 1
    while i < len(ordered):
        n = ordered[i]
        nt = n.type.upper() if isinstance(n.type, str) else str(n.type).upper()
        if nt not in ('LINE', 'CURVE', 'QCURVE'):
            offcurve_run.append(n); i += 1; continue  # off-curve: cuma dikumpulin dulu
        if nt == 'LINE':
            # garis lurus: SATU segmen sudah eksak (jarak segmen-ke-segmen
            # dihitung analitik di _seg_seg_dist), subdivide ke banyak titik
            # cuma nambah beban tanpa nambah akurasi -- cukup titik ujungnya.
            pts.append(node_xy(n))
        elif nt == 'CURVE':
            p0 = node_xy(prev)
            if len(offcurve_run) >= 2:
                p1, p2 = node_xy(offcurve_run[-2]), node_xy(offcurve_run[-1])
            elif len(offcurve_run) == 1:
                p1 = p2 = node_xy(offcurve_run[-1])
            else:
                p1 = p2 = p0
            _flatten_cubic(p0, p1, p2, node_xy(n), FLATTEN_TOL, 0, pts)
        elif nt == 'QCURVE':
            controls = [node_xy(c) for c in offcurve_run]
            if not controls:
                pts.append(node_xy(n))
            else:
                # >1 off-curve berturut-turut -> rantai quad dgn midpoint
                # implisit di antara tiap pasang off-curve bertetangga
                # (persis konvensi TrueType), bukan 1 segmen quad tunggal
                # yang cuma pakai off-curve TERAKHIR & buang sisanya.
                seg_start = node_xy(prev)
                for k in range(len(controls) - 1):
                    implied_end = _mid(controls[k], controls[k+1])
                    _flatten_quad(seg_start, controls[k], implied_end, FLATTEN_TOL, 0, pts)
                    seg_start = implied_end
                _flatten_quad(seg_start, controls[-1], node_xy(n), FLATTEN_TOL, 0, pts)
        prev = n
        offcurve_run = []
        i += 1
    return pts

def _get_base_layer(comp, ref_layer, font):
    try:
        bl = comp.componentLayer
        if bl is not None: return bl
    except Exception: pass
    name = getattr(comp,'componentName',None) or \
           getattr(getattr(comp,'component',None),'name',None)
    if not name: return None
    base_g = font.glyphs[name]
    if not base_g: return None
    for l in base_g.layers:
        if l.layerId==ref_layer.layerId or \
           l.associatedMasterId==ref_layer.associatedMasterId: return l
    return base_g.layers[0] if base_g.layers else None

def _decomposed_raw_nodes(layer, font, xform=(1,0,0,1,0,0)):
    """Kayak _all_polylines, tapi return NODE MENTAH (x,y,type) per path --
    bukan hasil sampling/flatten -- biar bisa dipakai bikin GSPath ASLI lagi
    (lihat check_area_overlap). Komponen tetap diratakan rekursif."""
    out = []
    for p in layer.paths:
        nodes = [(*_apply_xform(xform, n.position.x, n.position.y), n.type)
                  for n in p.nodes]
        out.append((nodes, bool(p.closed)))
    for comp in (layer.components or []):
        cxf = _mul_xform(xform, _comp_xform(comp))
        bl = _get_base_layer(comp, layer, font)
        if bl is None: continue
        out.extend(_decomposed_raw_nodes(bl, font, cxf))
    return out

def _all_polylines(layer, font):
    """List of sampled polylines (satu per path, komponen diratakan)."""
    polys = []
    for path in layer.paths: polys.append(_sample_path(path))
    for comp in (layer.components or []):
        xf = _comp_xform(comp)
        bl = _get_base_layer(comp, layer, font)
        if bl is None: continue
        for path in bl.paths: polys.append(_sample_path(path, xf))
        for sub in (bl.components or []):
            sub_bl = _get_base_layer(sub, bl, font)
            if sub_bl is None: continue
            cxf = _mul_xform(xf, _comp_xform(sub))
            for path in sub_bl.paths: polys.append(_sample_path(path, cxf))
    return [p for p in polys if len(p) >= 2]


# ══════════════════════════════════════════════════════════════════════════════
# PROFIL + POINT CLOUD
# profile : pita-Y -> tepi kiri/kanan (untuk prescreen cepat)
# cloud   : pita-Y -> daftar titik outline dekat tepi (untuk jarak 2D sejati)
# ══════════════════════════════════════════════════════════════════════════════

def _cleaned_polylines(layer, font, clean_cache=None):
    """
    Outline BERSIH: decompose + removeOverlap dulu (union boolean) supaya
    sliver/ekor self-intersection selebar-nol tidak dihitung sebagai tinta.
    Tanpa ini, pair seperti c+Z terbaca 'nempel' padahal tinta visualnya
    masih ada gap (sliver-nya yang bersilangan, bukan tintanya).

    OPTIMASI (aman, bukan aproksimasi): kalau layer HANYA berisi component
    (tanpa path sendiri) dan bounding-box antar component TIDAK bersinggungan
    sama sekali, maka removeOverlap tidak mengubah apa pun — union dari
    shape yang saling lepas = gabungan outline masing-masing apa adanya.
    Jadi decompose+removeOverlap (mahal) di-skip, diganti reuse outline
    bersih milik base glyph (dari clean_cache, kalau sudah dihitung) +
    sampling langsung shape lain. Kalau ada 1 pun bbox yang bersinggungan,
    atau layer bukan pure-component, langsung fallback ke jalur asli
    (100% sama seperti sebelumnya, tidak ada risiko hasil beda).
    """
    comps = layer.components or []
    if clean_cache is not None and not layer.paths and comps:
        resolved = []
        ok = True
        for comp in comps:
            xf = _comp_xform(comp)
            bl = _get_base_layer(comp, layer, font)
            if bl is None: ok = False; break
            bb = _layer_bbox_fast(bl, xf)
            if bb is None: ok = False; break
            resolved.append((xf, bl, bb))
        if ok:
            disjoint = True
            for i in range(len(resolved)):
                for j in range(i+1, len(resolved)):
                    if not _bbox_disjoint(resolved[i][2], resolved[j][2]):
                        disjoint = False; break
                if not disjoint: break
            if disjoint:
                pls = []
                for xf, bl, bb in resolved:
                    gname = getattr(getattr(bl, 'parent', None), 'name', None)
                    cached = clean_cache.get(gname) if gname else None
                    if cached is None:
                        cached = _cleaned_polylines(bl, font, clean_cache)
                        if gname: clean_cache[gname] = cached
                    if xf == (1,0,0,1,0,0):
                        pls.extend(cached)
                    else:
                        pls.extend([[_apply_xform(xf, x, y) for (x, y) in pl]
                                    for pl in cached])
                if pls: return pls
    try:
        work = layer.copyDecomposedLayer()
        try: work.removeOverlap()
        except Exception:
            try: work.removeOverlap_(True)
            except Exception: pass
        pls = [_sample_path(p) for p in work.paths]
        pls = [p for p in pls if len(p) >= 2]
        if pls: return pls
    except Exception:
        pass
    return _all_polylines(layer, font)   # fallback (outline mentah)

def _seg_band_xrange(x1, y1, x2, y2, b):
    """Rentang-x segmen setelah di-clip ke pita [b, b+Y_STEP]. None jika di luar."""
    if y1 == y2:
        if b <= y1 < b + Y_STEP or (y1 == b + Y_STEP):
            return (min(x1, x2), max(x1, x2))
        return None
    t0 = (b - y1) / (y2 - y1); t1 = (b + Y_STEP - y1) / (y2 - y1)
    if t0 > t1: t0, t1 = t1, t0
    t0 = max(t0, 0.0); t1 = min(t1, 1.0)
    if t0 > t1: return None
    xa = x1 + (x2 - x1) * t0; xb = x1 + (x2 - x1) * t1
    return (min(xa, xb), max(xa, xb))

def build_glyph_data(layer, font, polylines=None, clean_cache=None):
    if polylines is None:
        polylines = _cleaned_polylines(layer, font, clean_cache)
    if not polylines: return None
    segs = []
    for pl in polylines:
        for i in range(len(pl) - 1):
            (x1, y1), (x2, y2) = pl[i], pl[i+1]
            if x1 == x2 and y1 == y2: continue
            segs.append((x1, y1, x2, y2))
    if not segs: return None
    xmax = -1e18; xmin = 1e18
    for (x1, y1, x2, y2) in segs:
        if x1 > xmax: xmax = x1
        if x2 > xmax: xmax = x2
        if x1 < xmin: xmin = x1
        if x2 < xmin: xmin = x2
    # PASS 1: profil tepi per pita dari segmen TER-CLIP (bukan cuma titik —
    # segmen panjang hasil union tetap terhitung di semua pita yg dilintasi)
    left_p = {}; right_p = {}
    seg_bands = []
    for (x1, y1, x2, y2) in segs:
        b1 = int(min(y1, y2) // Y_STEP) * Y_STEP
        b2 = int(max(y1, y2) // Y_STEP) * Y_STEP
        blist = []
        b = b1
        while b <= b2:
            xr = _seg_band_xrange(x1, y1, x2, y2, b)
            if xr is not None:
                blist.append((b, xr))
                if b not in right_p or xr[1] > right_p[b]: right_p[b] = xr[1]
                if b not in left_p  or xr[0] < left_p[b]:  left_p[b]  = xr[0]
            b += Y_STEP
        seg_bands.append(blist)
    # PASS 2: indeks SEMUA segmen per pita dengan x ter-clip untuk pruning.
    # (Jangan difilter "dekat tepi" — perpotongan bisa terjadi jauh di dalam
    # bentuk pada pair yang overlap-nya dalam, mis. swash W/V/Z.)
    r_segs = {}; l_segs = {}
    for seg, blist in zip(segs, seg_bands):
        # PENTING: variabel loop di sini TIDAK BOLEH bernama xmin/xmax --
        # dulu memang begitu dan diam-diam MENIMPA xmin/xmax GLOBAL glyph
        # yang dihitung di atas (baris 250-255), karena Python tidak punya
        # scope per-blok. Akibatnya dataX["xmin"]/["xmax"] yang dipakai fast
        # bbox prescreen jadi cuma sisa band TERAKHIR yang diproses (bukan
        # bounding-box asli glyph) -> fast_gap salah -> banyak pair yang
        # SEBENARNYA nempel malah ke-fail duluan di fast prescreen tanpa
        # pernah sampai ke scan_gap/cloud_dist.
        for b, (bxmin, bxmax) in blist:
            r_segs.setdefault(b, []).append((bxmax, seg))
            l_segs.setdefault(b, []).append((bxmin, seg))
    for b in r_segs: r_segs[b].sort(key=lambda t: -t[0])   # xmax turun
    for b in l_segs: l_segs[b].sort(key=lambda t: t[0])    # xmin naik
    return {"left": left_p, "right": right_p,
            "r_cloud": r_segs, "l_cloud": l_segs,
            "xmin": xmin, "xmax": xmax}

def scan_gap(l_right, r_left, shift, reach_y=None):
    """
    Return (min_gap, band_kontak, ada_pita_bersama, cap).
    band_kontak = pita dengan |gap| terkecil (di situlah kontur paling dekat)
    cap = batas atas jarak vektor sejati (dari titik ekstrem pita tsb).
    """
    if reach_y is None: reach_y = Y_STEP  # baca live, bukan default beku
    best = None; babs = None; babs_band = None
    for y, lx in l_right.items():
        for dy in range(-reach_y, reach_y + Y_STEP, Y_STEP):
            rx = r_left.get(y + dy)
            if rx is None: continue
            g = (rx + shift) - lx
            if best is None or g < best: best = g
            ag = g if g >= 0 else -g
            if babs is None or ag < babs: babs = ag; babs_band = y
    if best is None: return None, None, False, None
    cap = (babs*babs + (reach_y + Y_STEP)**2) ** 0.5 + 0.5
    return best, babs_band, True, cap

def _pt_seg_d2(px, py, x1, y1, x2, y2):
    dx = x2 - x1; dy = y2 - y1
    L2 = dx*dx + dy*dy
    if L2 == 0:
        ex = px - x1; ey = py - y1; return ex*ex + ey*ey
    t = ((px - x1)*dx + (py - y1)*dy) / L2
    if t < 0: t = 0.0
    elif t > 1: t = 1.0
    ex = px - (x1 + t*dx); ey = py - (y1 + t*dy)
    return ex*ex + ey*ey

def _seg_seg_dist(a, b):
    """Jarak minimum dua segmen. 0 jika berpotongan (kontur bersilangan)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    d1x = ax2-ax1; d1y = ay2-ay1; d2x = bx2-bx1; d2y = by2-by1
    denom = d1x*d2y - d1y*d2x
    if denom != 0:
        t = ((bx1-ax1)*d2y - (by1-ay1)*d2x) / denom
        u = ((bx1-ax1)*d1y - (by1-ay1)*d1x) / denom
        if 0 <= t <= 1 and 0 <= u <= 1: return 0.0
    d2min = min(_pt_seg_d2(ax1, ay1, *b), _pt_seg_d2(ax2, ay2, *b),
                _pt_seg_d2(bx1, by1, *a), _pt_seg_d2(bx2, by2, *a))
    return d2min ** 0.5

def cloud_dist(r_segsA, l_segsB, shift, tol, start_band=None, cap=None, exact=False):
    """
    Jarak vektor 2D minimum antara segmen outline kanan A dan kiri B
    (digeser +shift). Berpotongan = 0. Early-exit begitu <= tol -- KECUALI
    exact=True.

    exact=True itu PENTING buat find_contact_kern (dipakai Fix): tanpa itu,
    begitu ketemu SATU kandidat yang sudah <= tol, fungsi ini langsung
    berhenti -- padahal kandidat itu belum tentu jarak MINIMUM yang
    sebenarnya (bisa jadi ada titik lain yang malah 0/nyilang beneran).
    Akibatnya nilai yang dipakai buat mutusin "ini kontak solid atau
    cuma nyerempet" jadi nggak konsisten (tergantung urutan pita mana yang
    kescan duluan), padahal PASS/FAIL di run_test tetap benar (early-exit
    aman buat pertanyaan ya/tidak <= tol). Jadi: run_test tetap pakai
    early-exit (cepat, cukup buat PASS/FAIL), find_contact_kern pakai
    exact=True (lambat dikit, tapi angkanya jadi jarak MINIMUM sungguhan).
    """
    if not r_segsA or not l_segsB: return 1e18
    best = cap if cap is not None else 1e18
    # PENTING -- guard wajib: kalau best/cap gede banget (mis. None dari
    # caller yang belum yakin ada pita bersama sama sekali), "reach" di
    # bawah bisa jadi ~1e18 dan while-loop-nya iterasi ratusan kuadriliun
    # kali per band A (mendekati infinite loop -> Glyphs.app hang total).
    # Klem ke rentang Y riil kedua glyph + sedikit margin -- itu batas atas
    # yang FISIK MASUK AKAL, nggak ada gunanya nyari lebih jauh dari situ.
    if l_segsB:
        yb_lo = min(l_segsB.keys()); yb_hi = max(l_segsB.keys())
    else:
        yb_lo = yb_hi = 0
    ya_lo = min(r_segsA.keys()); ya_hi = max(r_segsA.keys())
    MAX_REACH = (max(ya_hi, yb_hi) - min(ya_lo, yb_lo)) + Y_STEP * 4
    best = min(best, 1e18)
    if start_band is None: start_band = next(iter(r_segsA))
    # SEMUA pita A diperiksa (perpotongan bisa jauh dari pita awal),
    # diurutkan dari pita awal supaya early-exit cepat pada pair yg nempel.
    bandsA = sorted(r_segsA.keys(), key=lambda b: abs(b - start_band))
    for bA in bandsA:
        segsA = r_segsA[bA]
        reach = min(best + Y_STEP, MAX_REACH)
        bB = int((bA - reach) // Y_STEP) * Y_STEP
        bBmax = bA + reach
        while bB <= bBmax:
            segsB = l_segsB.get(bB)
            if segsB:
                for xmaxA, segA in segsA:            # xmax turun
                    if (segsB[0][0] + shift) - xmaxA > best:
                        break                        # segA berikut makin jauh
                    for xminB, sB in segsB:          # xmin naik
                        if (xminB + shift) - xmaxA > best:
                            break                    # segB berikut makin jauh
                        d = _seg_seg_dist(segA, (sB[0]+shift, sB[1],
                                                 sB[2]+shift, sB[3]))
                        if d < best:
                            best = d
                            if best <= tol and not exact: return best
                            if best == 0.0: return 0.0   # nggak mungkin lebih kecil dari 0
            bB += Y_STEP
    return best


# ══════════════════════════════════════════════════════════════════════════════
# KERNING — GROUP-AWARE
# ══════════════════════════════════════════════════════════════════════════════

def _kern_row_get(kdict, key):
    if key is None: return None
    try:
        row = kdict.get(key) if hasattr(kdict, 'get') else None
        if row is None:
            try: row = kdict[key]
            except Exception: row = None
        return row
    except Exception:
        return None

def effective_kern(font, mid, lg, rg):
    """Prioritas: glyph-glyph > glyph-group > group-glyph > group-group."""
    try: kdict = font.kerning[mid]
    except Exception: kdict = None
    lgrp = ("@MMK_L_" + lg.rightKerningGroup) if lg.rightKerningGroup else None
    rgrp = ("@MMK_R_" + rg.leftKerningGroup)  if rg.leftKerningGroup  else None
    if kdict is not None:
        lkeys = [(getattr(lg,'id',None), 'g'), (getattr(lg,'name',None), 'g')]
        if lgrp: lkeys.append((lgrp, 'G'))
        rkeys = [(getattr(rg,'id',None), 'g'), (getattr(rg,'name',None), 'g')]
        if rgrp: rkeys.append((rgrp, 'G'))
        seen=set(); lkeys=[k for k in lkeys if k[0] and not (k[0] in seen or seen.add(k[0]))]
        seen=set(); rkeys=[k for k in rkeys if k[0] and not (k[0] in seen or seen.add(k[0]))]
        for lk, ls in lkeys:
            row = _kern_row_get(kdict, lk)
            if row is None: continue
            for rk, rs in rkeys:
                v = _kern_row_get(row, rk)
                if v is not None and abs(v) < 100000:
                    return float(v), ls + rs
    combos = [(lg.name, rg.name, 'gg')]
    if rgrp: combos.append((lg.name, rgrp, 'gG'))
    if lgrp: combos.append((lgrp, rg.name, 'Gg'))
    if lgrp and rgrp: combos.append((lgrp, rgrp, 'GG'))
    for lk, rk, src in combos:
        try:
            v = font.kerningForPair(mid, lk, rk)
            if v is not None and abs(v) < 100000: return float(v), src
        except Exception: pass
    return 0.0, '—'


# ══════════════════════════════════════════════════════════════════════════════
# EXCLUDE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def build_unicode_map(font):
    umap = {}
    for g in font.glyphs:
        if g.unicode:
            hx = g.unicode.upper().zfill(4); umap[hx] = g.name
            try: umap[chr(int(hx,16))] = g.name
            except Exception: pass
    return umap

def parse_exclude_field(raw, font):
    umap = build_unicode_map(font); result = set()
    for token in re.split(r'[,\s]+', raw.strip()):
        token = token.strip()
        if not token: continue
        m = re.match(r'^[Uu]\+([0-9A-Fa-f]{4,6})$', token)
        if m:
            cp = m.group(1).upper().zfill(4)
            if cp in umap: result.add(umap[cp]); continue
        m = re.match(r'^[Uu][Nn][Ii]([0-9A-Fa-f]{4,6})$', token)
        if m:
            cp = m.group(1).upper().zfill(4)
            if cp in umap: result.add(umap[cp]); continue
        if re.match(r'^[A-Za-z0-9._-]+$', token):
            result.add(token); continue
        for char in token:
            if char in umap: result.add(umap[char])
    return result

def should_exclude(g, opts):
    if g.name in opts["exclude_custom"]: return True
    if opts["exported_only"] and not g.export: return True
    cat = (g.category or "").lower()
    if opts["exclude_marks"]   and cat == "mark": return True
    if opts["exclude_punct"]   and cat in ("punctuation","symbol","separator","other"): return True
    if opts["exclude_numbers"] and cat == "number": return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# FIX: cari kerning kontak via step+binary search pada jarak vektor
# ══════════════════════════════════════════════════════════════════════════════

def find_contact_kern(dataA, dataB, advance, start_kern, tol=None):
    """
    Cari kern (<= start_kern) supaya jarak vektor <= tol (kontak).
    Return kern kontak, atau None kalau tidak ketemu dalam MAX_KERN_SHIFT.
    """
    if tol is None: tol = TOUCH_TOL  # baca live, bukan default beku
    def D(k):
        shift = advance + k
        reach = int(tol // Y_STEP + 1) * Y_STEP
        g, band, had, cap = scan_gap(dataA["right"], dataB["left"], shift, reach_y=reach)
        if not had:
            # TIDAK ADA pita Y yang beririsan sama sekali -- artinya dua
            # outline ini emang beda ketinggian total, gak akan pernah
            # nempel cuma digeser horizontal (kerning nggak bisa gerakin
            # glyph naik/turun). Dulu ini jatuh ke cloud_dist(start_band=
            # None, cap=None) yang scan-nya nyaris tak berhingga -> Glyphs
            # hang. Sekarang langsung return jarak "sangat jauh" biar
            # find_contact_kern nyerah wajar (return None) tanpa nyoba
            # itung yang percuma & mahal.
            return 1e18
        if g is not None and g > tol:
            return g  # jarak >= gap horizontal; cukup utk melangkah
        # exact=True -- WAJIB di sini (lihat catatan di cloud_dist): find_
        # contact_kern butuh jarak MINIMUM sungguhan, bukan kandidat
        # pertama yg lolos tol, biar titik kontak yang ditemukan konsisten
        # & bukan hasil early-exit yang kebetulan.
        return cloud_dist(dataA["r_cloud"], dataB["l_cloud"], shift, tol,
                          start_band=band, cap=cap, exact=True)

    # Cek "had" itu TIDAK bergantung shift (cuma soal apa dua outline punya
    # pita-Y yang bertetangga sama sekali) -- kalau di satu shift nggak ada
    # irisan pita, di SEMUA shift juga nggak bakal ada (geser horizontal
    # nggak mengubah posisi vertikal). Jadi kalau sejak awal udah nggak ada
    # irisan pita, langsung nyerah sekarang -- daripada muter step-search
    # 200x percuma (tetep dijamin nggak infinite loop krn guard di atas,
    # tapi ini lebih cepat & jelas nggak-akan-pernah-nemu-nya).
    reach0 = int(tol // Y_STEP + 1) * Y_STEP
    _, _, had0, _ = scan_gap(dataA["right"], dataB["left"], advance + start_kern, reach_y=reach0)
    if not had0:
        return None

    k = float(start_kern)
    d = D(k)
    if d <= tol: return k
    contact = None      # kern dengan kontak (lebih negatif)
    no_contact = k      # kern tanpa kontak
    total = 0.0
    while total < MAX_KERN_SHIFT:
        step = max(d, 10.0)
        k -= step; total += step
        d = D(k)
        if d <= tol:
            contact = k; break
        no_contact = k
    if contact is None: return None
    # binary refine antara no_contact (belum) dan contact (sudah)
    while abs(no_contact - contact) > 0.5:
        m = (contact + no_contact) / 2.0
        if D(m) <= tol: contact = m
        else: no_contact = m
    return contact

def find_connect_kern(dataA, dataB, advance, start_kern,
                      tol=None, depth=-10):
    """
    Kern yang bikin pair nyambung:
    1. cari kern kontak (jarak vektor <= tol),
    2. tambah depth (overlap) -- itu doang. Nggak ada urusan panjang kontak
       minimum lagi, cukup nempel + sedalam `depth` = beres.
    """
    if tol is None: tol = TOUCH_TOL  # baca live, bukan default beku
    contact = find_contact_kern(dataA, dataB, advance, start_kern, tol)
    if contact is None: return None
    return contact + depth


# ══════════════════════════════════════════════════════════════════════════════
# UNION-AREA CHECK -- verifikasi kontak paling otoritatif yang ada
# ══════════════════════════════════════════════════════════════════════════════
# LATAR BELAKANG: buat pair yang nyentuh di sudut LANDAI (co. c+Z), jarak
# vektor titik-ke-titik bisa nunjukin "kontak" (bahkan persis 0, kurva
# beneran bersilangan) padahal pas di-zoom di node/outline view Glyphs.app
# keliatan cuma nyerempet -- karena persilangan sudut landai itu nggak bikin
# tinta BENERAN menyatu jadi satu bentuk, cuma numpang lewat deket.
#
# Cara paling otoritatif buat mastiin "connect": GABUNG dua outline jadi satu
# layer, jalanin removeOverlap() NATIVE Glyphs.app (mesin boolean yang sama
# dipakai buat nge-render font asli), terus bandingin luas tinta hasil
# gabungan vs jumlah luas A + luas B sendiri-sendiri. Kalau gabungannya lebih
# KECIL dari jumlah itu, berarti ada irisan tinta SUNGGUHAN (overlap area
# positif) -- bukan cuma nyerempet vektor. Ini persis ide "kalo di-combine
# dua huruf jadi satu, berarti udah connect" -- dan terbukti (lewat
# pengetesan independen pathops) jauh lebih akurat buat kasus sudut landai:
# titik kontak-vektor c+Z ada di sekitar -271, tapi overlap AREA positif baru
# muncul di -381 -- persis sama dengan hasil tes manual di Glyphs.app.

def _build_temp_layer(raw_paths, dx=0):
    """Bikin GSLayer BARU (bukan bagian glyph/font manapun) dari node mentah
    (lihat _decomposed_raw_nodes), digeser dx -- cuma wadah sementara buat
    manggil removeOverlap() native."""
    L = GSLayer()
    for nodes, closed in raw_paths:
        p = GSPath()
        for (x, y, t) in nodes:
            p.nodes.append(GSNode((x + dx, y), type=t))
        p.closed = closed
        L.paths.append(p)
    return L

def _layer_ink_area(layer):
    """Luas tinta TOTAL sebuah layer (signed sum per path via shoelace,
    dihitung dari flatten ADAPTIF/FLATTEN_TOL -- bukan sampling kasar).
    Sum signed otomatis nyubtract counter/lubang selama winding-nya
    konsisten dgn konvensi outline (itu selalu benar krn kita nggak pernah
    balik urutan node)."""
    total = 0.0
    for p in layer.paths:
        if not p.closed:
            continue  # path terbuka (sisa construction) tidak menutup tinta apa pun
        pts = _sample_path(p)
        n = len(pts)
        if n < 3: continue
        a = 0.0
        for i in range(n):
            x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % n]
            a += x1 * y2 - x2 * y1
        total += a * 0.5
    return total

def glyph_raw_and_area(layer, font):
    """Helper sekali-panggil per glyph: return (raw_nodes, area_sendiri).
    area dihitung dari layer BERSIH (decompose+removeOverlap dulu) via
    _build_temp_layer+_layer_ink_area, biar konsisten sama cara area
    gabungan dihitung nanti (bukan luas outline mentah yg mungkin masih ada
    sliver self-intersection)."""
    raw = _decomposed_raw_nodes(layer, font)
    tmp = _build_temp_layer(raw)
    try: tmp.removeOverlap()
    except Exception:
        try: tmp.removeOverlap_(True)
        except Exception: pass
    area = abs(_layer_ink_area(tmp))
    # ambil ulang node BERSIH (hasil removeOverlap) buat dipakai di gabungan
    # -- lebih murah drpd removeOverlap raw+B tiap kali (A udah dibersihin
    # sekali di sini, disimpan & dipakai ulang).
    clean_raw = []
    for p in tmp.paths:
        nodes = [(n.position.x, n.position.y, n.type) for n in p.nodes]
        clean_raw.append((nodes, bool(p.closed)))
    return clean_raw, area

def check_area_overlap(cleanA, areaA, cleanB, areaB, shift, min_overlap=None):
    """
    DEFINITIF: gabung outline BERSIH A (posisi asli) + outline BERSIH B
    (digeser shift) jadi satu layer, removeOverlap() NATIVE, lalu hitung
    overlap = (areaA + areaB) - luas_gabungan. overlap > min_overlap berarti
    BENERAN nyambung (irisan tinta nyata), bukan cuma nyerempet vektor.

    min_overlap default = MIN_OVERLAP_AREA (BUKAN toleransi "hampir nempel",
    tetap filosofi nempel=nempel) -- ini murni margin aman terhadap noise
    pembulatan: areaA/areaB/luas_gabungan itu angka BESAR (puluhan-ratusan
    ribu u^2), sedangkan overlap = selisihnya -- pengurangan dua angka besar
    yang hampir sama gampang kena galat pembulatan floating-point beberapa
    ratus u^2 (terverifikasi lewat pengetesan silang: dua cara hitung luas
    yang beda bisa selisih ~ratusan u^2 padahal bentuknya identik). Nilai
    dasarnya (300u^2 @ UPM 1000, kira2 lingkaran radius ~10u) di-skala
    KUADRATIK ke font.upm oleh _configure_scale_for_font -- cukup gede buat
    ngalahin noise itu di UPM manapun, masih cukup kecil buat nggak dianggap
    toleransi "shallow touch".

    Return (touching: bool, overlap_area: float).
    """
    if min_overlap is None: min_overlap = MIN_OVERLAP_AREA  # baca live, bukan default beku
    combined = _build_temp_layer(cleanA, dx=0)
    for nodes, closed in cleanB:
        p = GSPath()
        for (x, y, t) in nodes:
            p.nodes.append(GSNode((x + shift, y), type=t))
        p.closed = closed
        combined.paths.append(p)
    try: combined.removeOverlap()
    except Exception:
        try: combined.removeOverlap_(True)
        except Exception: pass
    area_ab = abs(_layer_ink_area(combined))
    overlap = (areaA + areaB) - area_ab
    return overlap > min_overlap, overlap

def find_solid_contact_kern(dataA, dataB, advance, start_kern,
                            cleanA, areaA, cleanB, areaB, tol=None):
    """
    Cari kern kontak yang DIVERIFIKASI union-area (bukan cuma jarak vektor).
    Langkah:
    1. Pakai find_contact_kern (cepat, jarak vektor) buat dapetin kandidat
       awal -- ini biasanya sudah dekat/benar utk kontak tegak lurus.
    2. Verifikasi kandidat itu pakai check_area_overlap (mahal tapi
       definitif). Kalau BELUM overlap area (kasus sudut landai kayak c+Z),
       lanjut geser makin negatif SELANGKAH DEMI SELANGKAH (step search,
       bukan binary -- overlap area terhadap kern nggak selalu monoton utk
       bentuk kompleks, jadi step kecil lebih aman drpd nebak arah) sampai
       overlap area positif ketemu.
    Return kern kontak yang BENERAN overlap-area, atau None.
    """
    contact = find_contact_kern(dataA, dataB, advance, start_kern, tol)
    if contact is None: return None
    k = contact
    touching, overlap = check_area_overlap(cleanA, areaA, cleanB, areaB,
                                           advance + k)
    if touching: return k
    step = max(Y_STEP, 5.0)
    total = 0.0
    while total < MAX_KERN_SHIFT:
        k -= step; total += step
        touching, overlap = check_area_overlap(cleanA, areaA, cleanB, areaB,
                                               advance + k)
        if touching: return k
    return None


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

class OptionsDialog:
    """
    Dialog Test cuma ngurusin: glyph mana yang dicek + toleransi nempel.
    Depth/min-contact (buat fitur Fix) SENGAJA nggak ada di sini -- itu
    diatur langsung di jendela Fix (PairsWindow) pas mau fix beneran,
    biar nggak ada field yang keliatan ikut nentuin PASS/FAIL padahal enggak.
    """
    def __init__(self, font):
        self.font = font
        W, PAD, ROW, SP = 400, 16, 22, 8
        H = 430
        self.w = vanilla.Window((W, H), "Check Pair Touch v3.1",
                                minSize=(W, H), maxSize=(W, H))
        y = PAD
        self.w.cb_exported = vanilla.CheckBox(
            (PAD+4, y, -PAD, ROW), "Test exported glyphs only", value=True)
        y += ROW + SP
        self.w.cb_marks = vanilla.CheckBox(
            (PAD+4, y, -PAD, ROW), "Exclude Marks (diacritics)", value=True)
        y += ROW + SP
        self.w.cb_punct = vanilla.CheckBox(
            (PAD+4, y, -PAD, ROW), "Exclude Punctuation && Symbols")
        y += ROW + SP
        self.w.cb_numbers = vanilla.CheckBox(
            (PAD+4, y, -PAD, ROW), "Exclude Numbers")
        y += ROW + SP*2
        self.w.lbl_custom = vanilla.TextBox(
            (PAD, y, -PAD, ROW), "Custom exclude (nama / char / U+XXXX):",
            sizeStyle="small")
        y += ROW
        self.w.tf_custom = vanilla.EditText(
            (PAD+4, y, -PAD, 26), placeholder="e.g.  braceleft braceright at")
        y += 26 + SP*2
        self.w.lbl_focus = vanilla.TextBox(
            (PAD, y, -PAD, ROW),
            "Focus glyph (opsional -- nama/char, pisah spasi/koma):",
            sizeStyle="small")
        y += ROW
        self.w.tf_focus = vanilla.EditText(
            (PAD+4, y, -PAD, 26), placeholder="e.g.  c Z   (kosong = semua glyph)")
        y += 26 + SP
        self.w.lbl_fhint = vanilla.TextBox(
            (PAD+4, y, -PAD, 20),
            "Kalau diisi: cuma pair yg salah satu sisinya glyph ini yang "
            "dites (jauh lebih cepat -- O(n) bukan O(n²)).",
            sizeStyle="small")
        y += 20 + SP
        self.w.cb_thorough = vanilla.CheckBox(
            (PAD+4, y, -PAD, ROW), "Thorough verify (union-area) -- lebih lambat")
        y += ROW
        self.w.lbl_thint = vanilla.TextBox(
            (PAD+4, y, -PAD, 28),
            "Verifikasi tambahan pakai gabung-outline (removeOverlap native) "
            "utk pair yg 'nempel tipis'/sudut landai (co. c+Z). Jauh lebih "
            "akurat tapi bikin Test All lebih lama -- pakai bareng Focus "
            "glyph di atas biar ringan.",
            sizeStyle="small")
        # Nggak ada field "touch tolerance" lagi -- definisi "nempel" itu
        # FIXED secara shape (TOUCH_TOL, jarak vektor asli hasil removeOverlap
        # + resolusi tinggi utk A-Z/a-z), bukan angka yang perlu diatur user.
        # Satu-satunya yang user atur ada di jendela Fix: Touch depth.

        self.w.btn_cancel = vanilla.Button(
            (PAD, -38, 90, 24), "Cancel", callback=lambda _: self.w.close())
        self.w.btn_run = vanilla.Button(
            (-PAD-110, -38, 110, 24), "Run Test ▶", callback=self._run)
        self.w.setDefaultButton(self.w.btn_run)
        self.w.open()

    def _get_opts(self):
        return {
            "exported_only":   self.w.cb_exported.get(),
            "exclude_marks":   self.w.cb_marks.get(),
            "exclude_punct":   self.w.cb_punct.get(),
            "exclude_numbers": self.w.cb_numbers.get(),
            "exclude_custom":  parse_exclude_field(self.w.tf_custom.get(), self.font),
            "thorough":        self.w.cb_thorough.get(),
            "focus_glyphs":    parse_exclude_field(self.w.tf_focus.get(), self.font),
            # tol & depth TIDAK di-set di sini -- tol pakai TOUCH_TOL tetap
            # (definisi nempel = shape, bukan angka yang diatur user), depth
            # diatur langsung di jendela Fix pas mau fix.
        }

    def _run(self, _):
        self.w.btn_run.enable(False); self.w.btn_run.setTitle("Running…")
        try: run_test(self.font, self._get_opts())
        finally:
            self.w.btn_run.enable(True); self.w.btn_run.setTitle("Run Test ▶")


class PairsWindow:
    def __init__(self, font, pairs, data_by_mid, widths_by_mid, opts):
        self.font = font; self.pairs = pairs
        self.data_by_mid = data_by_mid
        self.widths_by_mid = widths_by_mid
        self.tol = TOUCH_TOL   # fixed -- definisi "nempel" itu shape, bukan opsi user
        n = len(pairs)
        self.w = vanilla.Window((760, 540), f"Failing Pairs  ({n})", minSize=(600, 400))
        self.w.table = vanilla.List(
            (0, 0, -0, -132),
            [{"Left": p["left"], "Right": p["right"],
              "Dist": f"{p['dist']:.1f}", "Kern": f"{p['kern']:.0f}",
              "Src": p["src"], "Type": p["kind"], "Master": p["master"]}
             for p in pairs],
            columnDescriptions=[
                {"title": "Left",   "key": "Left",   "width": 180},
                {"title": "Right",  "key": "Right",  "width": 180},
                {"title": "Dist",   "key": "Dist",   "width": 60},
                {"title": "Kern",   "key": "Kern",   "width": 60},
                {"title": "Src",    "key": "Src",    "width": 40},
                {"title": "Type",   "key": "Type",   "width": 70},
                {"title": "Master", "key": "Master", "width": 90},
            ],
            allowsSorting=True, allowsMultipleSelection=True, drawFocusRing=False)

        self.w.line_fix = vanilla.HorizontalLine((0, -132, -0, 1))
        self.w.lbl_depth = vanilla.TextBox((12, -122, 100, 20), "Touch depth:")
        self.w.tf_depth = vanilla.EditText((112, -125, 52, 22),
                                           str(opts.get("depth", -10)))
        self.w.lbl_dhint = vanilla.TextBox(
            (176, -122, -12, 20),
            "negatif = seberapa dalam overlap (makin negatif makin dalam)",
            sizeStyle="small")
        self.w.cb_group = vanilla.CheckBox(
            (12, -96, -12, 20),
            "Tulis ke GROUP kerning bila ada (varian se-group ikut ter-fix; "
            "uncheck = exception per pair)", value=True, sizeStyle="small")
        self.w.btn_fix_sel = vanilla.Button(
            (12, -68, 130, 24), "Fix Selected", callback=self._fix_selected)
        self.w.btn_fix_all = vanilla.Button(
            (150, -68, 150, 24), "Fix + Verify All", callback=self._fix_all)
        self.w.lbl_fix_status = vanilla.TextBox((312, -64, -12, 20), "", sizeStyle="small")

        self.w.line_bar = vanilla.HorizontalLine((0, -36, -0, 1))
        self.w.btn_tab = vanilla.Button(
            (-290, -28, 200, 22), "Open All in Edit Tab",
            callback=self._open_tab, sizeStyle="small")
        self.w.btn_close = vanilla.Button(
            (-84, -28, 72, 22), "Close",
            callback=lambda _: self.w.close(), sizeStyle="small")
        self.w.open()

    def _get_depth(self):
        try: return float(self.w.tf_depth.get())
        except ValueError:
            vanilla.dialogs.message("Invalid depth", "Masukkan angka."); return None

    def _apply_fix(self, pairs_to_fix):
        depth = self._get_depth()
        if depth is None: return
        use_group = bool(self.w.cb_group.get())
        font = self.font
        fixed = 0; errors = 0; still_fail = []
        done_keys = set()      # group pair yang sudah DITULIS, jangan dobel
        kern_by_group = {}     # (mid, lk, rk) -> kern final yang ditulis

        clean_area_cache = {}   # (mid, name) -> (clean_raw, area) -- lihat
                                 # glyph_raw_and_area; sekali per glyph,
                                 # dipakai berkali-kali lintas pair.
        def _get_clean_area(mid, name):
            key = (mid, name)
            if key not in clean_area_cache:
                clean_area_cache[key] = glyph_raw_and_area(
                    font.glyphs[name].layers[mid], font)
            return clean_area_cache[key]

        font.disableUpdateInterface()
        try:
            for p in pairs_to_fix:
                lg = font.glyphs[p["left"]]; rg = font.glyphs[p["right"]]
                data = self.data_by_mid[p["mid"]]
                widths = self.widths_by_mid[p["mid"]]
                dataA = data[p["left"]]; dataB = data[p["right"]]
                adv = widths[p["left"]]
                cur_kern, _ = effective_kern(font, p["mid"], lg, rg)

                lgroup = lg.rightKerningGroup if use_group else None
                rgroup = rg.leftKerningGroup  if use_group else None
                lk = ("@MMK_L_" + lgroup) if lgroup else p["left"]
                rk = ("@MMK_R_" + rgroup) if rgroup else p["right"]
                key = (p["mid"], lk, rk)

                if key in kern_by_group:
                    new_kern = kern_by_group[key]
                else:
                    if lgroup or rgroup:
                        # PENTING: nulis ke GROUP mempengaruhi SEMUA pair
                        # yang berbagi grup itu -- termasuk pair yang TIDAK
                        # lagi di-fix sekarang (mis. base c+Z yang udah
                        # nempel duluan, sementara yang di-fix sekarang
                        # cuma c_braceright.liga+Z_braceright.liga). Kalau
                        # cuma pakai hasil pair yang lagi diproses, base
                        # c+Z bisa ke-timpa jadi kerning yang salah dan
                        # jadi TIDAK nempel lagi -- persis kasus yang
                        # ketahuan. Jadi: kumpulin SEMUA anggota grup (dari
                        # seluruh glyph yang datanya ada, bukan cuma yang
                        # gagal), cari titik kontak tiap anggota, ambil
                        # yang PALING NEGATIF (paling butuh dalam) supaya
                        # kern grup final dijamin bikin SEMUA anggota
                        # nempel real, baru baru ditambah depth.
                        left_members = [n for n in data
                                        if font.glyphs[n].rightKerningGroup == lgroup] \
                                       if lgroup else [p["left"]]
                        right_members = [n for n in data
                                         if font.glyphs[n].leftKerningGroup == rgroup] \
                                        if rgroup else [p["right"]]
                        worst_contact = None
                        for ln2 in left_members:
                            d2A = data.get(ln2)
                            if d2A is None: continue
                            adv2 = widths.get(ln2)
                            if adv2 is None: continue
                            cleanA2, areaA2 = _get_clean_area(p["mid"], ln2)
                            for rn2 in right_members:
                                d2B = data.get(rn2)
                                if d2B is None: continue
                                cleanB2, areaB2 = _get_clean_area(p["mid"], rn2)
                                ck2, _ = effective_kern(font, p["mid"],
                                                        font.glyphs[ln2], font.glyphs[rn2])
                                # find_solid_contact_kern -- BUKAN cuma jarak
                                # vektor, tapi diverifikasi union-area (gabung
                                # dua outline, removeOverlap native, cek luas
                                # irisan beneran positif). Ini yang bikin
                                # kasus sudut landai (co. c+Z) nggak berhenti
                                # di titik singgung tipis doang.
                                c = find_solid_contact_kern(d2A, d2B, adv2, ck2,
                                                            cleanA2, areaA2,
                                                            cleanB2, areaB2,
                                                            tol=self.tol)
                                if c is None: continue
                                if worst_contact is None or c < worst_contact:
                                    worst_contact = c
                        new_kern = (worst_contact + depth) if worst_contact is not None else None
                    else:
                        cleanA, areaA = _get_clean_area(p["mid"], p["left"])
                        cleanB, areaB = _get_clean_area(p["mid"], p["right"])
                        contact = find_solid_contact_kern(dataA, dataB, adv, cur_kern,
                                                          cleanA, areaA, cleanB, areaB,
                                                          tol=self.tol)
                        new_kern = (contact + depth) if contact is not None else None
                    kern_by_group[key] = new_kern
                if new_kern is None:
                    print(f"  ✗ {p['left']}+{p['right']}: kontak tidak ketemu "
                          f"dalam {MAX_KERN_SHIFT}u (termasuk anggota grup lain)"); errors += 1; continue
                new_kern_r = round(new_kern)
                if key not in done_keys:
                    try:
                        font.setKerningForPair(p["mid"], lk, rk, new_kern_r)
                        done_keys.add(key); fixed += 1
                    except Exception as e:
                        print(f"  ✗ write {lk}+{rk}: {e}"); errors += 1
                        continue

                # VERIFIKASI per-pair TETAP jalan sendiri-sendiri (murah --
                # cuma 1x scan_gap+cloud_dist, bukan search) biar composite
                # yang tintanya beda dari base (mis. brace nongol) tetap
                # ketahuan kalau ternyata masih gap/kelewat overlap walau
                # kern-nya nebeng base.
                v_kern, v_src = effective_kern(font, p["mid"], lg, rg)
                shift = adv + v_kern
                reach = int(self.tol // Y_STEP + 1) * Y_STEP
                g, band, had, cap = scan_gap(dataA["right"], dataB["left"], shift, reach_y=reach)
                d = cloud_dist(dataA["r_cloud"], dataB["l_cloud"], shift,
                               self.tol, start_band=band, cap=cap)
                if d > self.tol:
                    still_fail.append((p["left"], p["right"], d, v_kern, v_src))
        finally:
            font.enableUpdateInterface()

        status = f"✅ Fixed {fixed}"
        if errors: status += f" · ✗ {errors} error"
        if still_fail:
            status += f" · ⚠️ {len(still_fail)} MASIH GAP (Macro window)"
            print("\n⚠️  MASIH GAP SETELAH FIX (mis. composite dgn tinta beda "
                  "dari base yg nebeng kern-nya):")
            for l, r, d, k, s in still_fail:
                print(f"   {l} + {r}: dist={d:.1f}  kern tersimpan={k} ({s})")
        else:
            status += " · semua terverifikasi nempel ✔"
        self.w.lbl_fix_status.set(status)
        print(f"\nFix: {fixed} kerning ditulis ({len(kern_by_group)} unik dihitung "
              f"dari {len(pairs_to_fix)} pair) · verified OK: "
              f"{len(pairs_to_fix)-len(still_fail)-errors} · masih gap: {len(still_fail)}")

    def _fix_selected(self, _):
        sel = self.w.table.getSelection()
        if not sel:
            vanilla.dialogs.message("No selection", "Pilih baris dulu."); return
        self._apply_fix([self.pairs[i] for i in sel])

    def _fix_all(self, _):
        self._apply_fix(self.pairs)

    def _open_tab(self, _):
        seen = set(); parts = []
        for p in self.pairs:
            key = (p["left"], p["right"])
            if key not in seen:
                seen.add(key); parts.append(f"/{p['left']}/{p['right']}")
        self.font.newTab("".join(parts))


# ══════════════════════════════════════════════════════════════════════════════
# TEST RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_test(font, opts):
    _configure_scale_for_font(font)   # rescale Y_STEP/TOUCH_TOL/MIN_OVERLAP_AREA ke UPM font ini
    tol = TOUCH_TOL   # fixed -- "nempel" = kontak shape asli, bukan opsi user
    thorough = bool(opts.get("thorough", False))   # union-area verify (lambat)
    focus_glyphs = opts.get("focus_glyphs") or set()   # kosong = semua glyph
    # Kalau diisi: cuma pair yang salah satu sisinya (kiri ATAU kanan) ada
    # di focus_glyphs yang dites -- O(n) bukan O(n^2), jadi Thorough (union-
    # area, mahal) bisa dinyalain tanpa bikin Test All jadi lama banget.
    font_path   = font.filepath
    output_dir  = os.path.dirname(font_path) if font_path else os.path.expanduser("~/Desktop")
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f"pair_touch_report_v3.1_{timestamp}.txt")

    all_glyphs = list(font.glyphs)
    mode_label = "true vector + union-area (thorough)" if thorough else "true vector distance"
    focus_label = (f"   Focus : {', '.join(sorted(focus_glyphs))}" if focus_glyphs else "")
    lines = ["="*70,
             f"{font.familyName} — PAIR TOUCH v3.1 [{mode_label}]",
             f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}   "
             f"Tol : {tol}u{focus_label}",
             "="*70]

    grand_pass = grand_fail = grand_skip = 0
    n_falsepass = 0
    all_fail_pairs = []
    data_by_mid = {}; widths_by_mid = {}

    for master in font.masters:
        mid = master.id; mname = master.name
        active = []
        for g in all_glyphs:
            if should_exclude(g, opts): continue
            layer = g.layers[mid]
            if layer and (layer.paths or layer.components): active.append(g)

        print(f"[{mname}] Building profiles+clouds for {len(active)} glyphs…")
        data = {}
        clean_cache = {}
        # proses glyph non-composite (base) duluan supaya composite yang
        # cuma nge-ref base tsb bisa langsung reuse cache-nya (bukan
        # decompose+removeOverlap ulang dari nol).
        def _is_pure_component(g):
            layer = g.layers[mid]
            return bool(layer.components) and not layer.paths
        active_ordered = sorted(active, key=_is_pure_component)
        for g in active_ordered:
            layer = g.layers[mid]
            # Semua glyph sekarang dapet presisi kurva yang SAMA (adaptive
            # flatten, lihat FLATTEN_TOL) -- nggak perlu lagi bedain A-Z/a-z
            # vs glyph lain kayak dulu (SAMPLES_PER_SEG_STRICT).
            pls = _cleaned_polylines(layer, font, clean_cache)
            clean_cache[g.name] = pls
            d = build_glyph_data(layer, font, polylines=pls)
            if d: data[g.name] = d
        widths = {g.name: g.layers[mid].width for g in active}
        data_by_mid[mid] = data; widths_by_mid[mid] = widths

        fail_pairs = []; pass_count = skip_count = 0
        names = [g.name for g in active if g.name in data]
        gmap = {g.name: g for g in active}
        total = len(names); done = 0

        # cache (nama -> (clean_raw, area)) buat verifikasi union-area --
        # DIHITUNG SEKALI per glyph, cuma kalau beneran dipakai (lihat di
        # bawah), bukan di muka utk semua glyph (mahal & kebanyakan nggak
        # perlu).
        clean_area_cache = {}
        def _get_clean_area(name):
            if name not in clean_area_cache:
                clean_area_cache[name] = glyph_raw_and_area(gmap[name].layers[mid], font)
            return clean_area_cache[name]

        # Kalau focus_glyphs diisi, sisi yang SAMA SEKALI nggak nyentuh
        # focus_glyphs bisa langsung dilewatin di level luar (hemat lebih
        # banyak drpd cek per-pair di dalam) -- tapi tetap harus jaga pair
        # (focus, X) DAN (X, focus), makanya loop luar & dalam masing2 tetap
        # jalan ke semua `names`, cuma pair yg kedua sisinya non-focus yang
        # di-skip di iterasi dalam.
        for ln in names:
            lg = gmap[ln]; dataA = data[ln]; adv = widths[ln]
            ln_is_focus = (not focus_glyphs) or (ln in focus_glyphs)
            for rn in names:
                if focus_glyphs and not ln_is_focus and rn not in focus_glyphs:
                    continue   # kedua sisi di luar focus -- skip, nggak usah dites
                rg = gmap[rn]; dataB = data[rn]
                kern, src = effective_kern(font, mid, lg, rg)
                shift = adv + kern

                # O(1) Fast Pruning: Bounding box horizontal gap
                fast_gap = (dataB["xmin"] + shift) - dataA["xmax"]
                if fast_gap > tol:
                    fail_pairs.append({"left": ln, "right": rn, "dist": fast_gap,
                                       "kern": kern, "src": src, "kind": "gap",
                                       "master": mname, "mid": mid})
                    continue

                reach = int(tol // Y_STEP + 1) * Y_STEP
                g_h, band, had, cap = scan_gap(dataA["right"], dataB["left"], shift, reach_y=reach)
                if not had:
                    skip_count += 1; continue
                if g_h > tol:
                    # tidak ada overlap horizontal -> pasti tidak nempel
                    fail_pairs.append({"left": ln, "right": rn, "dist": g_h,
                                       "kern": kern, "src": src, "kind": "gap",
                                       "master": mname, "mid": mid})
                    continue
                # kandidat nempel -> verifikasi jarak vektor 2D
                d = cloud_dist(dataA["r_cloud"], dataB["l_cloud"], shift,
                               tol, start_band=band, cap=cap)
                if d <= tol:
                    # NEMPEL = jarak vektor sekarang <= tol. TAPI: kalau d
                    # BUKAN 0/nyaris-0 (bukan overlap dalam yg jelas), itu
                    # kandidat "kontak sudut landai" (co. c+Z) -- kurva bisa
                    # persis bersilangan (d=0 atau kecil) padahal TINTA-nya
                    # belum beneran menyatu jadi satu bentuk (lihat modul
                    # UNION-AREA CHECK di atas). Verifikasi definitif pakai
                    # union-area HANYA kalau opsi "thorough" dinyalain --
                    # ini mahal (gabung outline + removeOverlap native per
                    # pair), dan ternyata BANYAK pair borderline kayak gini
                    # (bukan cuma c+Z) jadi kalau selalu jalan bisa bikin
                    # Test All jauh lebih lambat. Default: percaya jarak
                    # vektor aja (cepat), user nyalain thorough kalau mau
                    # akurasi ekstra & rela nunggu lebih lama.
                    if thorough and d > 0.05:
                        cleanA, areaA = _get_clean_area(ln)
                        cleanB, areaB = _get_clean_area(rn)
                        touching, overlap = check_area_overlap(cleanA, areaA,
                                                               cleanB, areaB, shift)
                        if not touching:
                            n_falsepass += 1
                            fail_pairs.append({"left": ln, "right": rn, "dist": d,
                                               "kern": kern, "src": src,
                                               "kind": "marginal",
                                               "master": mname, "mid": mid})
                            continue
                    pass_count += 1
                else:
                    n_falsepass += 1
                    fail_pairs.append({"left": ln, "right": rn, "dist": d,
                                       "kern": kern, "src": src, "kind": "near2D",
                                       "master": mname, "mid": mid})
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{total} glyphs…")

        fail_pairs.sort(key=lambda x: -x["dist"])
        all_fail_pairs.extend(fail_pairs)
        grand_pass += pass_count; grand_fail += len(fail_pairs); grand_skip += skip_count

        lines += [f"\n{'─'*70}", f"MASTER : {mname}",
                  f"PASS : {pass_count}   FAIL : {len(fail_pairs)}   SKIP : {skip_count}",
                  f"{'─'*70}"]
        if fail_pairs:
            lines.append(f"{'LEFT':<24} {'RIGHT':<24} {'DIST':>8} {'KERN':>8} {'SRC':>4} {'TYPE':>7}")
            lines.append(f"{'-'*24} {'-'*24} {'-'*8} {'-'*8} {'-'*4} {'-'*7}")
            for p in fail_pairs:
                ks = f"{p['kern']:.0f}" if p["kern"] else "—"
                lines.append(f"{p['left']:<24} {p['right']:<24}"
                             f" {p['dist']:>8.1f} {ks:>8} {p['src']:>4} {p['kind']:>7}")
        else:
            lines.append("🎉 All pairs touching!")

    lines += [f"\n{'='*70}",
              f"SUMMARY · PASS {grand_pass} · FAIL {grand_fail} · SKIP {grand_skip}",
              f"'near2D' = {n_falsepass} pair yang lolos scanline v1/v2 "
              f"tapi TIDAK nempel secara vektor (mis. c+Z)",
              "="*70]

    report = "\n".join(lines)
    try:
        with open(report_path, "w", encoding="utf-8") as f: f.write(report)
        print(f"\n📄 Report: {report_path}")
    except Exception as e:
        print(f"(report tidak tersimpan: {e})")

    all_fail_pairs.sort(key=lambda x: -x["dist"])
    if vanilla is None: return all_fail_pairs
    if grand_fail == 0:
        vanilla.dialogs.message("🎉 Semua pair nempel.", f"{grand_pass} pair dicek.")
    else:
        if vanilla.dialogs.askYesNo(
                "Pair Touch v3.1 — Done",
                f"❌ {grand_fail} pair tidak nempel "
                f"({n_falsepass} di antaranya false-PASS di versi lama).\n"
                f"✅ {grand_pass} nempel (terverifikasi vektor).\n\nLihat & fix?"):
            PairsWindow(font, all_fail_pairs, data_by_mid, widths_by_mid, opts)
    return all_fail_pairs


# ══════════════════════════════════════════════════════════════════════════════
try:
    font = Glyphs.font
    if not font:
        print("No font open.")
    else:
        OptionsDialog(font)
except NameError:
    pass  # dijalankan di luar Glyphs (headless test)
