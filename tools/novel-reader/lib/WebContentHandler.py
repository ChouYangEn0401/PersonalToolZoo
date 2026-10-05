from playwright.sync_api import Playwright

# https://www.rouwennp.org/
def GetNovelContentFromUrl(playwright: Playwright, url) -> None:
    ## init
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(url)

    ## get content
    str__getNovelBookName(page)
    str__getNovelChapterName(page)
    strList__getNovelContent(page)

    context.close()
    browser.close()

global__NovelBookName = ""
def str__getNovelBookName(page):
    global global__NovelBookName
    if global__NovelBookName == "":
        links = page.locator("a[href^='https://www.rouwennp.org/book']").all()
        results = []
        for link in links:
            href = link.get_attribute("href")
            title = link.text_content().strip()
            if href and title:  # 確保不會擷取到空內容
                results.append((href, title))
        global__NovelBookName = results[0][-1]
        print(results, results[0], global__NovelBookName)
    return global__NovelBookName

global__NovelChapter = ""
def str__getNovelChapterName(page):
    global global__NovelChapter
    if global__NovelChapter == "":
        global__NovelChapter = page.locator("#mlfy_main_text h1").text_content().strip()
        print("取得小說章節:", global__NovelChapter)
    return global__NovelChapter

global__NovelContent = []
def strList__getNovelContent(page):
    global global__NovelContent
    if len(global__NovelContent)==0:
        text = page.locator("#TextContent").inner_text()
        # text = text.replace("\u2003", "")  ## 移除全形空白
        # text = text.strip()
        global__NovelContent = text
        print("取得小說內容:", global__NovelContent)
    return global__NovelContent
