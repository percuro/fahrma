# Renaming the product

The product is called "fahrma" (working name until 0.3: "Autokasse"). For a fork or a white-label instance, change:

1. `frontend/src/app/brand.ts`: `APP_NAME`, `APP_SHORT_NAME` (also feeds `index.html` and the web app manifest)
2. `backend/app/config.py`: `APP_NAME`, `APP_SLUG` (file names of the CSV export)
3. Repository and image name `percuro/fahrma` in `compose.yaml`, `README.md`, `docs/self-hosting.md` and `.github/ISSUE_TEMPLATE/config.yml`
4. Package names in `frontend/package.json` and `e2e/package.json` (cosmetic)
5. Contact address in `COMMERCIAL.md`
6. For a different look: the colours in `frontend/src/styles/theme.css` (and the two bar colours in `brand.ts`), the app icon `frontend/src/app/icon.svg` (then `node scripts/icons.mjs`) and the mark in `frontend/src/components/BrandMark.tsx`

`git grep -i "fahrma"` lists what is left. Internal names such as the session cookie `carshare_session`, the CSRF header `X-Carshare-CSRF`, the browser storage key `autokasse:last-group` and the database file `carshare.db` stay unchanged so that existing installations keep working.
