from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import re
import os

app = Flask(__name__)

# 從環境變數讀取憑證
google_credentials = os.getenv('GOOGLE_CREDENTIALS')  # 獲取環境變數

credentials_info = json.loads(google_credentials)  # 將 JSON 字符串轉換為字典
creds = Credentials.from_service_account_info(credentials_info)

# Google Sheets ID 和範圍（你需要更改為自己的 Sheet ID 和範圍）
SPREADSHEET_ID = '你需要更改為自己的 Sheet ID'
RANGE_NAME = 'Sheet1!A2:D'  # 假設資料寫入 A2 到 D 欄

# 設定權限範圍
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# 函數：將資料寫入 Google Sheets
def write_to_google_sheets(date_time, number, location, category):
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=creds)

    # 格式化日期為 YYYY/MM/DD
    formatted_date_time = date_time.replace("-", "/")
    
    # 讀取現有的資料
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])

    # 新資料
    new_row = [formatted_date_time, number, location, category]
    values.append(new_row)  # 將新資料加入現有資料

    # 按照日期欄位 (第一欄) 進行排序
    sorted_values = sorted(values, key=lambda row: datetime.strptime(row[0], "%Y/%m/%d"))

    # 寫入排序後的資料回 Google Sheets
    body = {
        'values': sorted_values
    }

    try:
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        print(f"Data written and sorted successfully!")
    except Exception as e:
        print(f"Error writing to Google Sheets: {e}")

# 使用正則表達式提取日期部分
def extract_date(date_time_str):
    match = re.match(r"(\d{4}-\d{2}-\d{2})", date_time_str)
    if match:
        return match.group(1)
    else:
        return None

# 處理記帳邏輯
def handle_account_intent(parameters):
    # 提取日期
    date_time = parameters.get('date-time')
    if date_time:
        date_time = extract_date(date_time)  # 用正則提取日期
    else:
        date_time = datetime.now().strftime('%Y-%m-%d')  # 預設為今天

    # 提取其他參數
    number = parameters.get('number')  # 金額
    category = parameters.get('Category')  # 類別
    location = parameters.get('location', {}).get('business-name', "")  # 地點

    # 驗證必要參數是否存在
    if not number or not category:
        return "記錄資料時有缺少必要參數，請再檢查輸入！"
    
    # 寫入 Google Sheets
    write_to_google_sheets(date_time, number, location, category)

    return f"已成功✐紀錄 {number} 元\n｜地點：{location}\n｜類別：{category}\n｜日期：{date_time}"

# 處理查詢邏輯
def handle_search_intent(parameters):
    date_time = parameters.get('date-time')
    print("Raw date-time from Dialogflow:", date_time)  # 查看原始輸入

    if not date_time:
        return "請提供您想查詢的日期。您可以說「今天的收支」或指定某個日期，例如「2024年12月3日的收支」"

    # 使用正則表達式提取日期並轉換為 YYYY/MM/DD
    extracted_date = extract_date(date_time)
    if not extracted_date:
        return "日期格式錯誤，請提供正確的日期，例如「2024年12月3日」或「今天」。"

    print("Formatted date-time for search:", extracted_date)  # Debug 格式化後的日期

    # 查詢收支資料
    expenses = get_expenses_by_date(extracted_date)

    if expenses:
        total_amount = 0  # 初始化金額總和
        response_text = f"✎{extracted_date}\n"
        for expense in expenses:
            amount = float(expense[1])
            total_amount += amount
            response_text += f"金額：{expense[1]}\n｜地點：{expense[2]}\n｜類別：{expense[3]}\n"

        response_text += f"\n總金額：{total_amount} 元"  # 顯示加總的金額
    else:
        response_text = f"沒有找到 {extracted_date} 的收支資料。"

    print("Response to user:", response_text)  # Debug 回覆給用戶的內容
    return response_text

# 從 Google Sheets 查詢指定日期的收支資料
def get_expenses_by_date(date_time):
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=creds)

    try:
        # 讀取 Google Sheets 中的資料
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])

        print("Fetched values from Sheets:", values)  # Debug: 查看 Sheets 中取回的資料

        # 格式化 date_time 為 YYYY/MM/DD
        formatted_date_time = date_time.replace("-", "/")  # 將日期格式化為 YYYY/MM/DD
        print(f"Formatted search date: {formatted_date_time}")  # Debug: 查看格式化後的日期

        # 篩選出日期匹配的資料
        filtered_expenses = []
        for row in values:
            sheet_date = row[0]  # 假設日期在第 0 欄

            print(f"Comparing sheet date: {sheet_date} with search date: {formatted_date_time}")  # Debug: 查看比較的日期

            if sheet_date == formatted_date_time:  # 日期匹配
                filtered_expenses.append(row)

        return filtered_expenses

    except Exception as e:
        print(f"Error reading from Google Sheets: {e}")
        return []

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        req = request.get_json(silent=True)
        print("Request JSON:", json.dumps(req, indent=2))  # 輸出完整請求到日誌
        intent_name = req.get('queryResult').get('intent').get('displayName')
        parameters = req.get('queryResult').get('parameters')
        print("Parameters:", parameters)  # 查看所有參數


        if intent_name == 'account':  # 記帳邏輯
            response_text = handle_account_intent(parameters)
        elif intent_name == 'search':  # 查詢收支邏輯
            response_text = handle_search_intent(parameters)
        else:
            response_text = "抱歉，我無法識別您的需求。請再試一次！"

        return jsonify({'fulfillmentText': response_text})

    except Exception as e:
        print(f"Error: {e}")
        return 'Internal server error', 500

if __name__ == '__main__':
    app.run(port=8080, debug=True)
