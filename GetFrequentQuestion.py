# -*- coding: utf-8 -*-
"""
@File  : GetFrequentQuestion.py
@Author: SangYu
@Date  : 2019/3/15 13:54
@Desc  : 获取常见问题集
"""
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
import time
import csv
import pickle
from threading import Thread
from queue import Queue


# 使用selenium连接网络，解决无法直接获得源代码的页面
def selenium_chrome(url):
    browser = webdriver.Chrome()
    browser.get(url)
    return browser


# 返回url连接
def request_url(url):
    headers = {'User-Agent': "Mozilla/5.0 (Windows NT 5.1; U; en; rv:1.8.1) Gecko/20061208 Firefox/2.0.0 Opera 9.50",
               "Connection": "close"}
    # 增加重连次数
    s = requests.session()
    s.keep_alive = False  # 关闭多余连接
    return s.get(url, headers=headers)


# 从阳光高考网获取常见问题集
# noinspection PyProtectedMember,PyUnusedLocal
def get_question_yggk():
    # 院校咨询页url
    main_url = "https://gaokao.chsi.com.cn"
    file_path = "Data"
    university_formid = []
    with open("university_info", "rb")as p_file:
        university_infos = pickle.load(p_file)
    for info in university_infos:
        if "985" in info["院校特性"] or "211" in info["院校特性"]:
            if info["forum_id"] != "":
                university_formid.append([info["院校名称"], info["forum_id"]])
    print("共有%d所985、211大学" % len(university_formid))
    for university in university_formid:
        begin = time.time()
        print("开始抓取" + university[0] + "的招生问题数据...")
        main_page_url = "https://gaokao.chsi.com.cn/zxdy/forum--method-listDefault,year-2005,forumid-" + university[
            1] + ",start-0.dhtml"
        try:
            main_page_source = request_url(main_page_url)
            main_page_source.encoding = main_page_source.apparent_encoding
            main_page_soup = BeautifulSoup(main_page_source.content, "lxml")
            # 获取页面总数，页面栏含有省略号、不含省略号两种查找方式
            if main_page_soup.find("li", class_="lip dot"):
                page_count = main_page_soup.find("li", class_="lip dot").next_sibling.a.string
            else:
                page_count = main_page_soup.find("ul", class_="ch-page clearfix").find_all("li")[-2].a.string
            # 置顶问题个数
            top_question_count = len(main_page_soup.find("table", class_="ch-table zx-table")
                                     .find_all("span", class_="question_top_txt"))
            print("页面总数：%d 置顶问题个数：%d" % (int(page_count), int(top_question_count)))
        except Exception as e:
            # 招生咨询页面没有数据（三个大学）
            print("%s咨询界面没有数据，页面链接为：%s" % (university[0], main_page_url))
            print("错误信息：%s" % e)
            continue
        # 创建该学校的问题集收集表,并写好表头
        table_head = ["标题", "来源", "时间", "问题", "回答"]
        csvfile = open(file_path + "/" + university[0] + "常用问题集.csv", "w", newline="", encoding='utf-8')
        csvfile.truncate()
        writer = csv.writer(csvfile)
        writer.writerow(table_head)
        record_queue = Queue()
        # 每次开启10个线程,进行数据下载和存储
        start_index = 0
        end_index = 10
        while True:
            if start_index > int(page_count):
                break
            else:
                dThread = [DownloadPageInfo(university[1], page_id, int(page_count), top_question_count, record_queue)
                           for page_id in
                           range(start_index, end_index)]
                sThread = SavePageInfo(record_queue, writer)
                for d in dThread:
                    d.start()
                sThread.start()
                for d in dThread:
                    d.join()
                record_queue.put(-1)
                sThread.join()
                start_index += 10
                end_index += 10
                if end_index > int(page_count):
                    end_index = int(page_count)

        csvfile.close()
        print("抓取%s的信息用时：%ds" % (university[0], time.time() - begin))


# 下载一页的信息
class DownloadPageInfo(Thread):
    def __init__(self, university_id, page_id, page_count, top_question_count, record_queue):
        Thread.__init__(self)
        self.university_id = university_id
        self.page_id = page_id
        self.page_count = page_count
        self.top_question_count = top_question_count
        self.record_queue = record_queue

    def get_page_info(self):
        main_url = "https://gaokao.chsi.com.cn"
        page_question_count = 15
        page_url = main_url + "/zxdy/forum--method-listDefault,year-2005,forumid-" + self.university_id + ",start-" + str(
            self.page_id * page_question_count) + ".dhtml"
        print("页面抓取进度(%d,%d)" % (self.page_id + 1, self.page_count))
        print("页面url %s" % page_url)
        try:
            page_source = request_url(page_url)
            page_source.encoding = page_source.apparent_encoding
            page_soup = BeautifulSoup(page_source.text, "lxml")
            # 获取咨询序列（所有的子节点）
            tr_list = page_soup.find("table", class_="ch-table zx-table").contents
            # 除去其中的空行
            for item in tr_list:
                if item == "\n":
                    tr_list.remove(item)
            # 置顶问答只记录一次
            if self.page_id == 0:
                start_index = 0
            else:
                start_index = self.top_question_count * 2
            page_infos = []
            for i_qa_pair in range(start_index, len(tr_list), 2):
                question_title = "q_title"
                question_from = ""
                question_time = ""
                question_text = "q_text"
                answer_text = "a_text"
                question_title = str(tr_list[i_qa_pair].find("a", class_="question_t_txt").string).strip().replace(",",
                                                                                                                   "，")
                # print("标题:%s" % question_title)
                question_from = str(tr_list[i_qa_pair].find("i", title="提问人").next_sibling.string).strip().replace(",",
                                                                                                                   "，")
                # print("来源:%s" % question_from)
                question_time = str(
                    tr_list[i_qa_pair].find("td", class_="question_t ch-table-center").text).strip().replace(",", "，")
                # print("时间:%s" % question_time)
                # 问题与答案可能出现本页无法写下的情况，需要进行页面跳转获取信息
                question_text_class = tr_list[i_qa_pair + 1].find("div", class_="question")
                if question_text_class.find(text='[详细]') is None:
                    question_text = str(question_text_class.text).strip()
                else:
                    turn_page_url = main_url + question_text_class.find("a", text='[详细]')["href"]
                    question_text = self.get_question_text(turn_page_url)
                replace_str = ["回复", "\n", "\r", "\t", "\xa0", "\ue63c", "\ue5e5", "\u3000" "[", "]", " "]
                for r_str in replace_str:
                    question_text = question_text.replace(r_str, "")
                question_text = question_text.replace(",", "，")
                # print("问题:%s" % question_text)
                answer_text_class = tr_list[i_qa_pair + 1].find("div", class_="question_a")
                if answer_text_class.find(text='[详细]') is None:
                    answer_text = str(answer_text_class.text).replace("[ 回复 ]", "").strip()
                else:
                    turn_page_url = main_url + answer_text_class.find("a", text='[详细]')["href"]
                    answer_text = self.get_answer_text(turn_page_url)
                replace_str = ["回复", "\n", "\r", "\t", "\xa0", "\ue63c", "\ue5e5", "\u3000" "[", "]", " "]
                for r_str in replace_str:
                    answer_text = answer_text.replace(r_str, "")
                answer_text.replace(",", "，")
                # print("回答:%s" % answer_text)
                page_infos.append([question_title, question_from, question_time, question_text, answer_text])
            return page_infos

        except Exception as e:
            print("错误信息%s" % e)
            return []

    def get_question_text(self, turn_page_url):
        try:
            turn_page_source = request_url(turn_page_url)
            turn_page_source.encoding = turn_page_source.apparent_encoding
            turn_page_soup = BeautifulSoup(turn_page_source.text, "lxml")
            question_text = str(turn_page_soup.find("div", class_="question").text).strip()
            return question_text
        except Exception as e:
            print("问句%s抓取失败,失败原因%s" % (turn_page_url, e))
            return ""

    def get_answer_text(self, turn_page_url):
        try:
            turn_page_source = request_url(turn_page_url)
            turn_page_source.encoding = turn_page_source.apparent_encoding
            turn_page_soup = BeautifulSoup(turn_page_source.text, "lxml")
            answer_text = str(turn_page_soup.find("div", class_="question_a").text).strip()
            return answer_text
        except Exception as e:
            print("答句%s抓取失败,失败原因%s" % (turn_page_url, e))
            return ""

    def run(self):
        page_record = self.get_page_info()
        if page_record:
            self.record_queue.put(page_record)


# 保存页面信息的线程
class SavePageInfo(Thread):
    def __init__(self, record_queue, writer):
        Thread.__init__(self)
        self.record_queue = record_queue
        self.writer = writer
        self.flag = 1

    def save_page_info(self, page_record):
        self.flag = 0
        for record in page_record:
            self.writer.writerow(record)
        self.flag = 1

    def run(self):
        while True:
            page_record = self.record_queue.get()
            if page_record == -1:
                break
            if page_record and self.flag:
                self.save_page_info(page_record)


# 从阳光高考网上获取本科大学（能够筛选出985、211）的院校代码信息
def get_undergraduate_university_info():
    # 院校库主页
    main_url = "https://gaokao.chsi.com.cn/sch/search.do?searchType=1&xlcc=bk&start="
    main_page_source = request_url(main_url + "0")
    main_page_source.encoding = main_page_source.apparent_encoding
    main_page_soup = BeautifulSoup(main_page_source.text, "lxml")
    page_count = int(main_page_soup.find("li", class_="lip dot").next_sibling.text)
    page_university_count = 20
    university_infos = []
    for i_page in range(page_count):
        page_url = main_url + str(i_page * page_university_count)
        print("页面抓取进度(%d,%d)" % (i_page + 1, int(page_count)))
        print("页面url%s" % page_url)
        browser = selenium_chrome(page_url)
        page_souce = browser.find_element_by_class_name("ch-table").get_attribute("innerHTML")
        browser.quit()
        page_soup = BeautifulSoup(page_souce, "lxml")
        page_soup.prettify()
        head = [th.text for th in page_soup.find("tr").find_all("th")]
        print(head)
        for tr in page_soup.find_all("tr")[1:]:
            info = {}
            td_list = tr.find_all("td")
            info["url"] = "https://gaokao.chsi.com.cn" + td_list[0].find("a")["href"]
            for i in [0, 1, 2, 3, 4, 7]:
                info[head[i]] = td_list[i].text.strip()
            info[head[5]] = td_list[5].text.strip().replace("\n", "").replace(" ", "").replace("\u2002", " ")
            info[head[6]] = td_list[6].text.strip().replace("\ue664", "有") if td_list[6].text.strip() != "" else "无"
            university_infos.append(info)
    for info in university_infos:
        print(info)
    with open("Information/大学/university_info", "wb")as p_file:
        pickle.dump(university_infos, p_file)


# 从阳光高考网上获取学校咨询论坛的id
def get_consultation_forum_id():
    with open("university_info", "rb")as p_file:
        university_infos = pickle.load(p_file)
    for i_info in range(len(university_infos)):
        info = university_infos[i_info]
        # if "985" not in info["院校特性"] and "211" not in info["院校特性"]:
        #     continue
        print(info)
        try:
            page_source = request_url(info["url"])
            page_source.encoding = page_source.apparent_encoding
            forum_id = \
                BeautifulSoup(page_source.text, "lxml").find("a", class_="ch-btn zx-question")["href"].split("-")[-1][
                :-6]
            print(forum_id)
        except:
            forum_id = ""
        university_infos[i_info]["forum_id"] = forum_id
    with open("university_info", "wb")as p_file:
        pickle.dump(university_infos, p_file)
    for info in university_infos:
        if "985" in info["院校特性"] and "211" in info["院校特性"]:
            print(info)


if __name__ == '__main__':
    # get_undergraduate_university_info()
    # get_consultation_forum_id()
    time_s = time.time()
    get_question_yggk()
    print("总共用时：%ds" % (time.time() - time_s))
    # with open("university_info", "rb")as p_file:
    #    university_infos = pickle.load(p_file)
    # for info in university_infos:
    #    if "985" in info["院校特性"] or "211" in info["院校特性"]:
    #        print(info)
