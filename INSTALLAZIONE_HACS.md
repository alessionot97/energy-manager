# Energy Manager — installazione e aggiornamenti con HACS

## 1. Pubblicazione su GitHub (una sola volta)

Crea un repository **pubblico** e vuoto, senza README, chiamato `energy-manager` su `alessionot97`:
https://github.com/new

Se la connessione GitHub di ChatGPT non ha accesso al repository, autorizza l'app GitHub dall'interfaccia di ChatGPT e ripeti il caricamento. In alternativa, puoi pubblicare i file dal tuo Mac con i seguenti comandi, dopo aver scaricato `energy-manager-v0.0.1.bundle` in `~/Downloads`:

```bash
cd ~/Downloads
git clone energy-manager-v0.0.1.bundle energy-manager
cd energy-manager
git remote set-url origin https://github.com/alessionot97/energy-manager.git
git push -u origin main
git push origin v0.0.1
```

Per creare la release GitHub (consigliato), apri **Releases → Draft a new release** nel repository, seleziona il tag `v0.0.1`, titolo `Energy Manager v0.0.1 beta` e pubblica la release. Per la beta spunta **Pre-release**.

## 2. Registrazione HACS dall'interfaccia Home Assistant

1. Se HACS non è già presente, installalo seguendo https://www.hacs.xyz/docs/use/download/download/ e completane l'onboarding.
2. In Home Assistant apri **HACS → ⋮ → Repository personalizzati** (Custom repositories).
3. URL: `https://github.com/alessionot97/energy-manager`
4. Categoria: **Integration / Integrazione** → Aggiungi.
5. Cerca **Energy Manager**, clicca **Scarica/Download** e conferma la versione.
6. Riavvia Home Assistant.
7. Vai in **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Energy Manager**.
8. Configura sensori e interruttori reali e verifica i segni: PCC > 0 = immissione; batteria > 0 = ricarica. Configura gli `rest_command` OpenEVSE.
9. Prima di consentire il comando dei carichi, disabilita le vecchie automazioni che li gestiscono. Non cancellare le definizioni REST né gli helper richiesti.

## 3. Aggiornamenti

A ogni nuova versione, incrementare `custom_components/energy_manager/manifest.json` (`version`), eseguire test/CI, creare un nuovo commit e tag Git (es. `v0.0.2`) e pubblicare una release GitHub. HACS rileverà la release e permetterà l'aggiornamento via interfaccia; è consigliato riavviare Home Assistant dopo ogni aggiornamento.

## Avvertenze beta

Il progetto comanda realmente carichi elettrici. Non sostituisce protezioni dell'impianto e va inizialmente verificato su Home Assistant, soprattutto per l'effettiva azione di `rest_command.evse_start`, `evse_stop` e `evse_set_amp`. L'helper `input_boolean.wallbox` non è un feedback fisico di stato. La prima installazione non è stata ancora collaudata su un Home Assistant reale.
