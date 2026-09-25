"""Calibre Argon2id sur ce PC ; aucune donnée ou clé utilisateur n'est utilisée.

Usage : python scripts/bench_memoire_crypto.py [--appliquer]
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.memoire_crypto import Coffre


def benchmark(maximum_mib=256):
    import psutil
    budget = min(maximum_mib, max(64, int(psutil.virtual_memory().available / 8 / 1024**2)))
    mem = max(m for m in (64, 128, 256, 512) if m <= budget)
    essais = []
    for cout in range(2, 11):
        mesures = []
        p = dict(memoryCost=mem*1024, timeCost=cout, parallelism=1, algorithmVersion=19)
        for _ in range(3):
            c = Coffre()
            t = time.perf_counter()
            c.creer('benchmark', 'phrase jetable de calibration', p)
            mesures.append((time.perf_counter()-t)*1000)
            c.fermer()
        ms = statistics.median(mesures)
        essais.append(dict(**p, mediane_ms=round(ms, 1)))
        if ms >= 250:
            break
    # Si le plus petit coût dépasse déjà 500 ms, réduire la RAM et recommencer.
    if essais[0]['mediane_ms'] > 500 and mem > 64:
        return benchmark(mem//2)
    choisi=min(essais, key=lambda e:abs(e['mediane_ms']-375))
    return dict(parametres={k:v for k,v in choisi.items() if k!='mediane_ms'},
                mediane_ms=choisi['mediane_ms'], essais=essais,
                bibliotheque='PyNaCl / libsodium', objectif_ms=[250,500])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--appliquer',action='store_true')
    args=parser.parse_args()
    resultat=benchmark()
    if args.appliquer:
        from core.config import definir
        definir('memoire.crypto',resultat['parametres'])
    print(json.dumps(resultat,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
