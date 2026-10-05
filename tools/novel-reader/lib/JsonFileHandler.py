import json
import os

JSON_FILE_DATA = None

def jsonFileReader(filename):
    global JSON_FILE_DATA
    """讀取 JSON 檔案，如果不存在則返回空字典"""
    try:
        with open(filename, "r", encoding="utf-8") as file:
            JSON_FILE_DATA = json.load(file)
            if JSON_FILE_DATA is None:
                JSON_FILE_DATA = {}
            return JSON_FILE_DATA
    except json.JSONDecodeError:
        print(f"文件 {filename} 格式错误，返回空字典")
        JSON_FILE_DATA = {}
        return JSON_FILE_DATA
    except FileNotFoundError:
        print(f"文件 {filename} 未找到，返回空字典")
        return {}

def jsonFileSaver(filename, data = None):
    global JSON_FILE_DATA
    """儲存 JSON 檔案，確保 UTF-8 格式"""
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data if data is not None else JSON_FILE_DATA, file, ensure_ascii=False, indent=4)


def editData(modes, book_name, main_link="", read_to=0, new_name=""):
    global JSON_FILE_DATA

    if JSON_FILE_DATA is None:
        print("Json File Not Init Yet !!")
        return

    """新增、刪除、重新命名或儲存書籍資訊"""
    for mode in modes:
        if mode in ['a', 'add', 'append', 'forceUpdate']:  # 新增或更新書籍
            if book_name in JSON_FILE_DATA and not (mode=="forceUpdate"):
                print(f"⚠️ 新名稱不可用或已存在：{new_name}")
            else:
                JSON_FILE_DATA[book_name] = {
                    "mainBookLink": main_link,
                    "readTo": read_to
                }
                print(f"✅ 已新增書籍：{book_name}")
        elif mode in ['editChange']:  # 新增或更新書籍
            data = editData(['get'], book_name)
            JSON_FILE_DATA[book_name] = {
                "mainBookLink": data["mainBookLink"] if main_link=="" else main_link,
                "readTo":  data["readTo"] if read_to=="" else read_to
            }
            print(f"✅ 已更新書籍：{book_name}")
        elif mode in ['del', 'delete']:  # 刪除書籍
            if book_name in JSON_FILE_DATA:
                del JSON_FILE_DATA[book_name]
                print(f"🗑️ 已刪除書籍：{book_name}")
            else:
                print(f"⚠️ 書籍不存在，無法刪除：{book_name}")
        elif mode in ['rename']:  # 重新命名書籍
            if book_name in JSON_FILE_DATA:
                if new_name and new_name not in JSON_FILE_DATA:
                    JSON_FILE_DATA[new_name] = JSON_FILE_DATA.pop(book_name)
                    print(f"✏️ 已將《{book_name}》更名為《{new_name}》")
                else:
                    print(f"⚠️ 新名稱不可用或已存在：{new_name}")
            else:
                print(f"⚠️ 書籍不存在，無法重新命名：{book_name}")
        elif mode in ['g', 'get']:  # 儲存變更
            if book_name==None:
                return JSON_FILE_DATA
            elif book_name in JSON_FILE_DATA:
                return JSON_FILE_DATA[book_name]
        elif mode in ['check-exist']:  # 儲存變更
            if book_name == None:
                return True
            return book_name in JSON_FILE_DATA
        # elif mode in ['s', 'save']:  # 儲存變更
        #     jsonFileSaver(filename, data)
        #     print("💾 已儲存 JSON 檔案")

def cleanData():
    global JSON_FILE_DATA
    JSON_FILE_DATA = None

def functionTesting01(json_file_name):
    jsonFileReader(json_file_name)
    editData(['add'], "novelName1", "novelMainPageLink.html", 100)
    editData(['add'], "novelName2", "novelMainPageLink.html", 0)
    editData(['rename'], "novelName2", new_name="novelName2_rename")
    editData(['del'], "novelName1")
    jsonFileSaver(json_file_name)