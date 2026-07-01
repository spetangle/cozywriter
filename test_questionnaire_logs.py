"""问卷日志测试脚本

运行方式: python test_questionnaire_logs.py

该脚本模拟完整的问卷流程，用于验证日志是否正常输出：
1. 创建问卷
2. 回答部分问题
3. 跳过问卷（AI补全）
4. 根据问卷创建项目
"""
import requests
import json
import time

BASE_URL = "http://localhost:13567/api/questionnaires"


def print_separator(title):
    """打印分隔线"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def create_questionnaire():
    """创建问卷"""
    print_separator("1. 创建问卷")
    payload = {"title": "测试问卷 - 科幻题材"}
    response = requests.post(f"{BASE_URL}", json=payload)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 创建成功，问卷ID: {result['id']}")
        print(f"  标题: {result['title']}")
        print(f"  当前步骤: {result['current_step']}")
        print(f"  状态: {result['status']}")
        return result["id"]
    else:
        print(f"✗ 创建失败: {response.text}")
        return None


def answer_step(q_id, question_id, answer, is_custom=False):
    """回答问卷步骤"""
    print(f"\n→ 回答问题: {question_id} = {answer}")
    payload = {
        "question_id": question_id,
        "answer": answer,
        "is_custom": is_custom
    }
    response = requests.post(f"{BASE_URL}/{q_id}/answer-step", json=payload)
    if response.status_code == 200:
        result = response.json()
        print(f"  ✓ 回答成功，下一步: {result['current_step']}")
        return result
    else:
        print(f"  ✗ 回答失败: {response.text}")
        return None


def skip_to_ai(q_id):
    """跳过问卷，AI补全"""
    print_separator("3. 跳过问卷（AI补全）")
    response = requests.post(f"{BASE_URL}/{q_id}/skip-to-ai")
    if response.status_code == 200:
        result = response.json()
        print(f"✓ AI补全成功")
        print(f"  补全字段数: {len(result['ai_answers'])}")
        print(f"  补全内容:")
        for key, value in result['ai_answers'].items():
            preview = value[:50] + "..." if len(value) > 50 else value
            print(f"    - {key}: {preview}")
        return result
    else:
        print(f"✗ AI补全失败: {response.text}")
        return None


def build_project(q_id):
    """根据问卷创建项目"""
    print_separator("4. 根据问卷创建项目")
    response = requests.post(f"{BASE_URL}/{q_id}/build-project")
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 项目创建成功")
        print(f"  项目ID: {result['project_id']}")
        print(f"  项目标题: {result['project_title']}")
        return result
    else:
        print(f"✗ 项目创建失败: {response.text}")
        return None


def run_full_test():
    """运行完整测试流程"""
    print("🚀 开始问卷日志测试...")
    print(f"目标服务: {BASE_URL}")
    
    # 1. 创建问卷
    q_id = create_questionnaire()
    if not q_id:
        print("❌ 测试终止：问卷创建失败")
        return
    
    time.sleep(0.5)
    
    # 2. 回答部分问题（模拟用户填写）
    print_separator("2. 回答部分问题")
    
    # 第1步：题材
    answer_step(q_id, "genre", "科幻")
    time.sleep(0.3)
    
    # 第2步：主题
    answer_step(q_id, "theme", "人工智能与人类的共存")
    time.sleep(0.3)
    
    # 第3步：基调（使用自定义答案）
    answer_step(q_id, "tone", "悬疑紧张", is_custom=True)
    time.sleep(0.3)
    
    # 3. 跳过问卷（AI补全剩余部分）
    skip_to_ai(q_id)
    time.sleep(0.5)
    
    # 4. 创建项目
    build_project(q_id)
    
    print_separator("测试完成")
    print("\n📋 请查看服务器日志验证以下内容：")
    print("  1. [问卷] 创建问卷日志")
    print("  2. [问卷] 回答步骤日志（每步一条）")
    print("  3. [问卷] AI补全日志（含缺失字段、补全结果）")
    print("  4. [问卷] 项目创建日志（含答案、篇幅估算、记录创建）")
    print("\n日志文件位置: data/logs/cozywriter_YYYYMMDD.log")


if __name__ == "__main__":
    run_full_test()