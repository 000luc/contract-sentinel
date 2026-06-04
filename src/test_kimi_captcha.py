"""
测试 Kimi API 识别验证码准确率
"""

import json
import base64
import os
from openai import OpenAI

BASE_DIR = r"D:\BaiduSyncdisk\claude\Contract Sentinel"
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "data", "logs")


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def recognize_with_kimi(image_path, api_key):
    """使用 Kimi API 识别验证码"""
    base64_image = encode_image(image_path)

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.kimi.com/v1"
    )

    response = client.chat.completions.create(
        model="kimi-latest",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "这是一张验证码图片。请只告诉我验证码中的字符是什么，不要任何解释，只返回验证码内容。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        max_tokens=50
    )

    result = response.choices[0].message.content.strip()
    # 清理结果，只保留字母和数字
    result = ''.join(c for c in result if c.isalnum())
    return result


def test_kimi_on_saved_captchas():
    """测试 Kimi 对之前保存的验证码的识别准确率"""
    config = load_config()
    api_key = config.get("kimi_api_key", "")

    if not api_key:
        print("错误：config.json 中没有找到 kimi_api_key")
        return

    print("=" * 50)
    print("测试 Kimi API 识别验证码")
    print("=" * 50)

    # 获取之前保存的验证码图片
    captcha_files = []
    for f in sorted(os.listdir(SCREENSHOT_DIR)):
        if f.startswith("accuracy_test_") and f.endswith(".png"):
            captcha_files.append(os.path.join(SCREENSHOT_DIR, f))

    if len(captcha_files) == 0:
        print("未找到之前保存的验证码图片")
        return

    print(f"\n找到 {len(captcha_files)} 张验证码图片，开始识别...\n")

    results = []
    for i, captcha_path in enumerate(captcha_files[:5]):  # 先测5张
        print(f"第 {i+1}/5 张: {os.path.basename(captcha_path)}")
        try:
            recognized = recognize_with_kimi(captcha_path, api_key)
            results.append({
                'file': os.path.basename(captcha_path),
                'recognized': recognized
            })
            print(f"  Kimi 识别结果: '{recognized}'")
        except Exception as e:
            print(f"  识别失败: {e}")
            results.append({
                'file': os.path.basename(captcha_path),
                'recognized': f"ERROR: {e}"
            })

    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    for r in results:
        print(f"{r['file']}: {r['recognized']}")

    print("\n请对照验证码图片，告诉我 Kimi 的识别准确率。")


if __name__ == "__main__":
    test_kimi_on_saved_captchas()
