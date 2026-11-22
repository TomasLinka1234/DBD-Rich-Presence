Stáhni **DbD-Rich-Presence.exe** a spusť ho. Návod je v [NAVOD.md](https://github.com/{REPO}/blob/main/NAVOD.md).

### Ověření souboru

Tenhle `.exe` sestavil GitHub Actions automaticky z veřejného zdrojového kódu, nikdo ho nenahrával ručně.

- commit: [`{SHORT}`](https://github.com/{REPO}/commit/{SHA})
- záznam sestavení: [{RUN}]({RUN})
- SHA256: `{HASH}`

Kontrola otisku (PowerShell):

```
Get-FileHash .\DbD-Rich-Presence.exe -Algorithm SHA256
```

Kontrola podepsaného původu (GitHub CLI):

```
gh attestation verify DbD-Rich-Presence.exe --repo {REPO}
```

Co program dělá a kam se připojuje: [SECURITY.md](https://github.com/{REPO}/blob/main/SECURITY.md).
