# kdroid-updates

ערוץ העדכונים של אפליקציית Kdroid Filter (מותאם אישית).

## איך דוחפים עדכון
1. מקבלים APK חדש עם מספר גרסה גבוה יותר (למשל 1.0.1).
2. יוצרים Release חדש עם תג `v1.0.1` ומעלים אליו את ה-APK בשם `kdroid.apk`.
3. מעדכנים כאן את `api.json`:
   - `version` = מספר הגרסה החדש (למשל "1.0.1")
   - `url` = קישור ההורדה של ה-APK מה-release
4. באפליקציה: לוחצים "בדוק עדכונים" → ההורדה וההתקנה אוטומטיות.

פורמט api.json:
```json
{ "version": "1.0.1", "url": "https://github.com/EliyahuHillel/kdroid-updates/releases/download/v1.0.1/kdroid.apk" }
```
