# פרסום הפרוטוטייפ והפעלת עדכון אוטומטי

## 1. העלאה ראשונה ל-GitHub

המאגר המיועד הוא:

```text
https://github.com/hiski88/ShebaOncTool
```

ב-Windows:

1. מתקינים Git for Windows.
2. מחלצים את קובץ הפרויקט.
3. לוחצים לחיצה ימנית על `PUBLISH_TO_GITHUB.ps1` ובוחרים Run with PowerShell, או מריצים מתוך PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\PUBLISH_TO_GITHUB.ps1
```

הסקריפט משכפל את המאגר, מעתיק רק קובצי קוד בטוחים, יוצר commit ומעלה ל-branch בשם `main`.

הסקריפט אינו מעלה:

- קובצי XLS או XLSX
- קובצי ICS
- נתוני עובדים
- תיקיית data
- Streamlit secrets

## 2. חיבור ל-Streamlit Community Cloud

1. נכנסים ל-Streamlit Community Cloud עם חשבון GitHub.
2. בוחרים Create app.
3. בוחרים repository בשם `hiski88/ShebaOncTool`.
4. בוחרים branch בשם `main`.
5. מגדירים Main file path כ-`app.py`.
6. מבצעים Deploy.

לאחר החיבור החד-פעמי, כל push חדש ל-GitHub גורם ל-Streamlit לבנות מחדש את האפליקציה אוטומטית.

## 3. חיבור Google Calendar

ב-Google Cloud Console:

1. יוצרים Project.
2. מפעילים Google Calendar API.
3. מגדירים OAuth consent screen.
4. יוצרים OAuth Client מסוג Web application.
5. מוסיפים Authorized redirect URI הזהה לכתובת האפליקציה ב-Streamlit.

ב-Streamlit App settings מוסיפים Secrets:

```toml
[google_oauth]
client_id = "YOUR_GOOGLE_OAUTH_CLIENT_ID"
client_secret = "YOUR_GOOGLE_OAUTH_CLIENT_SECRET"
redirect_uri = "https://YOUR-APP.streamlit.app"
state_secret = "RANDOM_LONG_SECRET"
```

אפשר ליצור `state_secret` מקומי באמצעות:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

בשלב הפרוטוטייפ מומלץ להשאיר את מסך ההסכמה של Google במצב Testing ולהוסיף את אנשי הצוות הרלוונטיים כ-Test users. אין להעלות את הערכים האמיתיים ל-GitHub.

## 4. בדיקת תקינות

GitHub Actions מריץ אוטומטית בכל push:

```text
compileall
pytest
```

יש לוודא שבכרטיסיית Actions מופיע סימון ירוק לפני שימוש בפרוטוטייפ.
