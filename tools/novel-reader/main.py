import os
import re
import json
from playwright.sync_api import Playwright, sync_playwright, expect
import subprocess

import lib.FileManagementhandler
from lib.FileManagementhandler import global__CurrentSavingPath
from lib.FileManagementhandler import genFolder, delFile
from lib.WebContentHandler import str__getNovelBookName, str__getNovelChapterName, strList__getNovelContent
from lib.WebContentHandler import global__NovelBookName, global__NovelChapter, global__NovelContent
from lib.WebContentHandler import GetNovelContentFromUrl
from lib.AudioProcessingHandler import strPath__localGenAudioForNovelContent, SpeedUpAudio
from lib.JsonFileHandler import jsonFileReader, jsonFileSaver, editData, JSON_FILE_DATA

global__JSON_FILE = "data/book_links.json"

def GenerateAudioFromNovelUrl(targetUrl):
    with sync_playwright() as playwright:
        ## search for novel
        GetNovelContentFromUrl(playwright, targetUrl)
        ## refresh data
        global__NovelBookName = lib.WebContentHandler.global__NovelBookName
        global__NovelChapter = lib.WebContentHandler.global__NovelChapter
        global__NovelContent = lib.WebContentHandler.global__NovelContent
        ## folder gen
        genFolder(global__NovelBookName)
        ## refresh data
        global__CurrentSavingPath = lib.FileManagementhandler.global__CurrentSavingPath

        ## audio gen
        old_mp3_path = strPath__localGenAudioForNovelContent(global__CurrentSavingPath, global__NovelContent, global__NovelChapter + ".mp3")
        ## audio speed up
        # --> using google gtts is prefect, but will have to handle the text length
        # --> using pyttsx3 will make file corrupted and can not be speed up
        # --> keep the audio un-speed-up for now !!
        # speed_ratio = 1.5
        # SpeedUpAudio(old_mp3_path, f"{global__CurrentSavingPath}{global__NovelChapter}({speed_ratio}).mp3", speed_ratio)
        # speed_ratio = 1.75
        # SpeedUpAudio(old_mp3_path, f"{global__CurrentSavingPosition}{global__NovelChapter}({speed_ratio}).mp3", speed_ratio)
        # speed_ratio = 2
        # SpeedUpAudio(old_mp3_path, f"{global__CurrentSavingPosition}{global__NovelChapter}({speed_ratio}).mp3", speed_ratio)


def printMenu():
    print("命令清單：")
    print("1. 輸入 'menu' 或 'help' 查看命令清單")
    print("2. 輸入 'exit' 或 'quit' 退出程序")
    print("3. 輸入 'BookList' 查看觀看紀錄")
    print("4. 輸入 'CreateBook' 製作新故事書音檔")
    print("5. 輸入 'SaveBookUpdate' 儲存變更")
    print("6. 輸入 'PlayAudio' 聆聽故事")
    print("7. 輸入 'DataBase' 打開音檔資料夾")
    print("")

def GenAudioFromOldBook():
    pass
    print("update in next version !!")

def GenAudioFromNewBook():
    targetUrl = input('輸入\'小說該章節網址\' -->')
    GenerateAudioFromNovelUrl(targetUrl)
    bookName = input("輸入\'小說名稱\' -->")
    if 'y' == input('是否記錄觀看進度？ -(y/n)->'):
        read_to = int(input("\'該章節進度數值\' -->"))
        if editData(['check-exist'], bookName):
            editData(['editChange'], bookName, "", read_to)
        else:
            bookLink = input("輸入\'小說主業網址\' -->")
            editData(['add'], bookName, bookLink, read_to)

def main():
    global global__JSON_FILE
    jsonFileReader(global__JSON_FILE)
    printMenu()

    while True:
        command= input("请输入命令（输入 'menu' 清單）：").strip()

        if command in ['menu', 'help']:
            printMenu()
        elif command.lower() in ['exit', 'quit']:
            print("程序已退出")

        elif command == 'BookList':
            print(editData(['get'], None))
        elif command == 'CreateBook':
            if 'y'==input('是否為新書？ -(y/n)->'):
                GenAudioFromNewBook()
            else:
                GenAudioFromOldBook()

        elif command == 'SaveBookUpdate':
            jsonFileSaver(global__JSON_FILE)
        elif command == 'PlayAudio':
            # audio_path_file
            print("sor, not develop yet !!")
        elif command == 'DataBase':
            print("sor, not develop yet !!")

        else:
            print("no this command found !!")

if __name__ == "__main__":
    main()
