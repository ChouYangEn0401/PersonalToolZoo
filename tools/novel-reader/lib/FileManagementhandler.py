import os

def delFile(file_path):
    if not os.path.exists(file_path): return
    if not os.path.isfile(file_path): return
    os.remove(file_path)

global__CurrentSavingPath = ""
def genFolder(folder_name):
    global global__CurrentSavingPath
    global__CurrentSavingPath = f"output/{folder_name}/"
    if not os.path.exists(global__CurrentSavingPath):
        os.mkdir(global__CurrentSavingPath)