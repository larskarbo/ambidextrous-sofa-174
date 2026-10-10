"""Independent exact cross-check of a certificate on a random sample of leaves.

For each sampled leaf box E it checks, in exact rational arithmetic, that
    leaf_bound (the paper's Gamma test, from the paper's own Python checker)  <= T,  or
    telescoping bound (re-implemented here independently of cchk2.c)         <= T.
Usage: python sample_check.py spec.json cert.txt sample_rate seed
"""
import json
import random
import sys

sys.path.insert(0, sys.argv[5] if len(sys.argv) > 5 else ".")
from check_cert_core import F, area, cut, initial_box, leaf_bound, parse_spec  # noqa: E402


def shape(hallways, W, prm, skip):
    """Polygons of B_W cap the shapes {g <= gd+1, f <= fb+1, (f >= fa or (f <= fa, g >= gc))} of all
    hallways except `skip`; prm[j] = (fa, fb, gc, gd)."""
    polys = [[(F(0), F(0)), (W, F(0)), (W, F(1)), (F(0), F(1))]]
    for j, (f, g) in enumerate(hallways):
        if j == skip:
            continue
        fa, fb, gc, gd = prm[j]
        new = []
        for P in polys:
            P = cut(cut(P, g, -1, gd + 1), f, -1, fb + 1)
            if len(P) < 3:
                continue
            P1 = cut(P, f, +1, fa)
            if len(P1) >= 3:
                new.append(P1)
            P2 = cut(cut(P, f, -1, fa), g, +1, gc)
            if len(P2) >= 3:
                new.append(P2)
        polys = new
    return [P for P in polys if area(P) > 0]


def slab_area(polys, fn, lo, hi, extra):
    """Area of the union of polys cap {lo <= fn <= hi} cap extra, extra = [(fn, sense, bound)]."""
    s = F(0)
    for P in polys:
        P = cut(cut(P, fn, +1, lo), fn, -1, hi)
        for e in extra:
            P = cut(P, *e)
        s += area(P)
    return s


def telescoping(hallways, W, box, n):
    K = len(hallways)
    uni, core, cen = [], [], []
    for j in range(K):
        (a, b), (c, d) = box[2 * j], box[2 * j + 1]
        if b - a > 2 or d - c > 2:
            return None
        uni.append((a, b, c, d))
        core.append((b, a, d, c))
        cen.append(((a + b) / 2, (a + b) / 2, (c + d) / 2, (c + d) / 2))
    total = sum(area(P) for P in shape(hallways, W, cen, -1))
    U = shape(hallways, W, uni, -1)
    for j, (f, g) in enumerate(hallways):
        (a, b), (c, d) = box[2 * j], box[2 * j + 1]
        C = shape(hallways, W, core, j)
        for coord in (0, 1):
            P, Q = (f, g) if coord == 0 else (g, f)
            lo_, hi_ = (a, b) if coord == 0 else (c, d)
            m, h = (lo_ + hi_) / 2, (hi_ - lo_) / 2
            if h == 0:
                continue
            t = [h * k / n for k in range(n + 1)]
            best = F(0)
            # increase
            loss_cond = [(Q, -1, c if coord == 0 else a)]
            for k in range(n):
                gain = slab_area(U, P, m + 1, m + 1 + t[k + 1], [])
                loss = slab_area(C, P, m, m + t[k], loss_cond) if k else F(0)
                best = max(best, gain - loss)
            # decrease
            lo_cut, hi_cut = (d, c + 1) if coord == 0 else (b, a + 1)
            loss_cond = [(Q, -1, (c if coord == 0 else a) + 1)]
            for k in range(n):
                if lo_cut < hi_cut:
                    gain = slab_area(U, P, m - t[k + 1], m, [(Q, -1, lo_cut)]) + slab_area(
                        U, P, m - t[k + 1], m, [(Q, +1, hi_cut)])
                else:
                    gain = slab_area(U, P, m - t[k + 1], m, [])
                loss = slab_area(C, P, m + 1 - t[k], m + 1, loss_cond) if k else F(0)
                best = max(best, gain - loss)
            total += best
    return total


def main():
    spec = json.load(open(sys.argv[1]))
    hallways, W, T = parse_spec(spec)
    n = int(spec.get("nsub", 0))
    rate, seed = float(sys.argv[3]), int(sys.argv[4])
    rng = random.Random(seed)
    root = initial_box(hallways, W)
    ncoord = len(root)
    # walk: per coordinate (depth, position); interval = lo + width * [pos, pos+1] / 2^depth
    depth, pos = [0] * ncoord, [0] * ncoord
    stack = []  # (k, upper?)
    checked = by_gamma = by_tele = 0
    worst = F(0)
    def stream(path, chunk=1 << 24):
        rest = ""
        with open(path) as fh:
            while True:
                block = fh.read(chunk)
                if not block:
                    break
                parts = (rest + block).split()
                rest = "" if block[-1].isspace() else parts.pop()
                yield from parts
        if rest:
            yield rest

    for tok in stream(sys.argv[2]):
        if tok != "L":
            k = int(tok)
            stack.append([k, 0])
            depth[k] += 1
            pos[k] *= 2
            continue
        if rng.random() < rate:
            box = []
            for i in range(ncoord):
                lo, hi = root[i]
                wdt = (hi - lo) / (2 ** depth[i])
                box.append((lo + wdt * pos[i], lo + wdt * (pos[i] + 1)))
            v = leaf_bound(hallways, W, box, T)
            if v <= T:
                by_gamma += 1
            else:
                v = telescoping(hallways, W, box, n) if n else None
                if v is None or v > T:
                    print("FAIL at a leaf", [(float(a), float(b)) for a, b in box], float(v) if v else None)
                    sys.exit(1)
                by_tele += 1
            worst = max(worst, v)
            checked += 1
        # move to next node
        while stack and stack[-1][1] == 1:
            k, _ = stack.pop()
            depth[k] -= 1
            pos[k] //= 2
        if not stack:
            break
        stack[-1][1] = 1
        pos[stack[-1][0]] += 1
    print(f"sampled leaves {checked}: {by_gamma} by Gamma, {by_tele} by the telescoping bound; "
          f"worst {float(worst):.10f} <= T = {float(T)}; ALL SAMPLED LEAVES PASS")


main()
