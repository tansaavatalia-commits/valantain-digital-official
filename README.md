# Valantain Digital: fabbrica di stampabili

Questo repository produce in serie prodotti digitali stampabili: planner, tracker, budget e checklist.
Ogni prodotto esce pronto da vendere su **Etsy**, **Gumroad** e **Payhip**.

Si scrive **un file YAML** e la fabbrica genera tutte le combinazioni di tema × lingua. Per ognuna produce:

- i PDF in ogni formato carta (A4, US Letter, A5), con indice cliccabile per GoodNotes e Notability
- 6 immagini di presentazione in formato 4:3 a 2400×1800 px, la risoluzione consigliata da Etsy
- titolo, 13 tag e descrizione, già entro i limiti Etsy
- lo ZIP da consegnare al cliente, con il file di licenza
- un `manifest.json` per prodotto, più `catalog.csv` e `gumroad-payhip.csv` per l'intero catalogo

Il catalogo di partenza conta **2 linee e 30 prodotti** (90 PDF e 180 immagini). Su 4 core si genera in circa 4 minuti.

## Il flusso di lavoro

```
catalog/*.yaml ──► validate ──► render PDF ──► controlli ──► mockup ──► testi ──► ZIP ──► CSV
   (idea)          (schema)     (WeasyPrint)  (pagine,     (Pillow)   (template  (Etsy:  (catalogo)
                                              20 MB)                  o Claude)  ≤20 MB)
```

1. **Idea.** Scegli una nicchia e scrivi un YAML in `catalog/`, partendo da uno di quelli esistenti.
2. **Controllo.** `python -m factory validate` verifica temi, lingue, formati e testi mancanti.
3. **Produzione.** `python -m factory build` genera tutto in `dist/`. La build è **incrementale**: i prodotti con specifica e codice invariati vengono saltati.
4. **Verifica.** Apri qualche PDF e le immagini in `dist/<linea>/<sku>/images/`.
5. **Pubblicazione.** Carica ZIP, immagini e `listing.txt` su Etsy, Gumroad o Payhip (dettagli sotto).
6. **Misura.** Dopo 2–4 settimane guarda quali temi e lingue vendono e produci altre varianti di quelli.

## Avvio rapido

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ai]"

python -m factory validate                     # controlla il catalogo
python -m factory list                         # elenca tutti gli SKU
python -m factory build                        # produce tutto in dist/
python -m factory build --only planner-2027-sage-it   # un solo prodotto
python -m factory build --copy claude          # testi scritti da Claude (serve ANTHROPIC_API_KEY)
python -m factory preview --sku planner-2027-sage-it  # HTML da aprire nel browser per ritoccare il design
pytest -q
```

Su Linux WeasyPrint richiede Pango (`apt-get install libpango-1.0-0 libpangoft2-1.0-0`). Su macOS basta `brew install pango`.

## Aggiungere una linea di prodotti

```yaml
line: meal-planner              # slug: diventa parte dello SKU
category: planner
name:     {it: Meal Planner, en: Meal Planner, es: Planificador de comidas}
subtitle: {it: Pasti e spesa della settimana, en: Weekly meals & groceries, es: Comidas y compra}
keywords: {it: [meal planner, lista spesa], en: [meal planner, grocery list], es: [menú semanal]}
pages:
  - type: cover
  - type: index                 # attiva i link interni (e la frase nelle inserzioni)
  - type: weekly
    repeat: 4                   # senza `year:` le pagine sono senza date: non scadono mai
  - type: checklist
    repeat: 4
  - type: notes
    options: {style: squares}   # lines | dots | squares
themes: [minimal, sage, blush, ocean, terracotta, lavender]
langs: [it, en, es]
sizes: [A4, Letter]
price: {eur: 3.90, usd: 4.50}
```

Tipi di pagina disponibili: `cover`, `index`, `year`, `monthly`, `weekly`, `daily`, `habit`,
`budget` (con `options.categories` per lingua), `checklist`, `goals`, `notes`.
Con `year: 2028` mesi e settimane vengono generati con le date reali. `week_start: sunday` serve per il mercato USA.

Nuovi temi vanno in `factory/themes.py`, nuove lingue in `factory/i18n.py`.
Il design di tutte le pagine sta in un unico template: `factory/templates/document.html.j2`.

## Automazione su GitHub

| Workflow | Quando parte | Cosa fa |
|---|---|---|
| `ci.yml` | ogni push e PR | lint (ruff), validazione del catalogo, test |
| `build.yml` | push su `main` che tocca `catalog/` o `factory/`, oppure a mano da **Actions → Produzione catalogo → Run workflow** | produce il catalogo e lo pubblica come artifact scaricabile (ZIP, immagini, testi, CSV) |
| `build.yml` su tag `v*` | `git tag v1.0 && git push --tags` | allega gli ZIP a una **Release**: è l'archivio delle versioni vendute |
| `dependabot.yml` | ogni mese | aggiorna dipendenze e azioni |

Per i testi scritti da Claude in CI, aggiungi il secret `ANTHROPIC_API_KEY` in
**Settings → Secrets and variables → Actions** e scegli `copy: claude` all'avvio del workflow.
Se Claude non risponde, la build usa i testi da template e non si ferma.

## Strumenti open source usati

| Strumento | Ruolo |
|---|---|
| [WeasyPrint](https://github.com/Kozea/WeasyPrint) | HTML/CSS → PDF vettoriale con link interni |
| [Jinja2](https://github.com/pallets/jinja) | template delle pagine |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | PDF → immagini per i mockup e i controlli |
| [Pillow](https://github.com/python-pillow/Pillow) | composizione delle immagini delle inserzioni |
| [Pydantic](https://github.com/pydantic/pydantic) | validazione delle specifiche YAML |
| [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) | testi delle inserzioni con Claude (opzionale) |
| [Inter](https://github.com/rsms/inter) e [Fraunces](https://github.com/undercasetype/Fraunces) | font con licenza OFL, uso commerciale consentito, inclusi in `factory/assets/fonts` |
| GitHub Actions, [action-gh-release](https://github.com/softprops/action-gh-release), Dependabot | produzione automatica, archivio delle versioni, aggiornamenti |

Gli strumenti sono stati scelti di proposito, invece di integrarne il più possibile: ogni dipendenza in più è
qualcosa che può rompersi. Questi coprono l'intera catena dall'idea al file venduto.

## Come pubblicare

**Etsy** (la fonte principale di traffico per gli stampabili):
1. Crea l'inserzione con tipo **Digitale**.
2. Carica le 6 immagini da `images/` (la `01-copertina` è la miniatura).
3. Copia titolo, tag e descrizione da `listing.txt`.
4. Carica lo ZIP come file digitale. Se supera i 20 MB, la fabbrica indica nel manifest di caricare i PDF singoli.
5. Etsy addebita 0,20 $ per inserzione più circa il 10% di commissioni sulle vendite. Inizia con 10–20 inserzioni, non con tutte.

**Gumroad / Payhip**: crea il prodotto, allega lo ZIP e usa `gumroad-payhip.csv` come scheda (nome, prezzo, descrizione, copertina).
Nessuna delle due piattaforme ha un import CSV ufficiale. Sono ottime per vendere ai tuoi follower e non hanno costi per inserzione.

## Prossimi passi possibili

- **Pubblicazione automatica su Etsy** tramite Open API v3 (bozze di inserzioni con immagini e file).
  Servono una app Etsy approvata e il dominio `openapi.etsy.com` abilitato nell'ambiente.
- Nuove linee: meal planner, planner per studenti, wedding planner, fitness tracker.
- Pin Pinterest generati dalle stesse pagine (formato verticale 1000×1500).
