# DEVELOPMENT_NOTES

Denne filen samler trygge observasjoner som gjør senere vedlikehold enklere.

## Frontend og Node-oppsett

Det ser ut til at den aktive frontend-appen bruker:
- `frontend/package.json`

Denne har normale scripts:
- `npm run dev`
- `npm run build`
- `npm run start`
- `npm run lint`

## Viktig observasjon om repo-roten

Repo-roten har også en `package.json`, men den inneholder bare:
- `date-fns`

Det betyr trolig ett av to:
1. den er en historisk rest
2. den brukes til noe veldig smalt og lokalt

Så lenge tjenesten er i bruk bør den **ikke** ryddes eller endres automatisk uten verifikasjon.

## Viktig observasjon om frontend-duplisering

Det finnes også:
- `frontend/frontend/package.json`

Dette bør senere avklares før opprydding.
Per nå bør man anta at:
- `frontend/package.json` er den viktigste
- `frontend/frontend/` kan være historisk eller midlertidig
- ingen automatisk sletting bør gjøres i en lavrisiko-runde

## Praktisk anbefaling for senere kontrollert opprydding

Når drift kan røres tryggere:
1. verifiser hvilken `package.json` som faktisk brukes i normale utviklerflyter
2. verifiser om `frontend/frontend/` er død kode eller aktiv rest
3. verifiser om rot-`package.json` har noen reell rolle
4. rydde først etter at dette er bekreftet

## Formål

Denne filen skal redusere risikoen for at senere opprydding treffer feil Node-/frontend-struktur.
