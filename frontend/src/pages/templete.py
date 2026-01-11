"""
COMMAND TEMPLATES (FastAPI → Chat.jsx)

이 파일은 step 함수 작성 시 참고용 템플릿 모음입니다.

payload 구조만으로 Chat.jsx의 입력값이 결정됩니다.

예외적으로 표가 나오면 마음에 들어요(마음에 드는 식물 선택 체크박스가 나옵니다)와 상세입력(채팅 활성 버튼)이 아래 붙어 나오게 되어있습니다.
"""

# ----------------------------------------
# 1. 선택지 버튼 (options)
# ----------------------------------------

# TEMPLATE
def step_x_choice():
    return {
        "messages": [bot("질문 문장")],
        "payload": {
            "question": "질문 문장",
            "options": ["선택1", "선택2"]
        }
    }

# EXAMPLE
def step_1():
    return {
        "messages": [bot("반려동물이 있으신가요?")],
        "payload": {
            "question": "반려동물이 있으신가요?",
            "options": ["있음", "없음"]
        }
    }


# ----------------------------------------
# 2. 텍스트 입력 (text)
# ----------------------------------------

# TEMPLATE
def step_x_text():
    return {
        "messages": [bot("텍스트를 입력해주세요.")],
        "payload": {
            "question": "텍스트 입력",
            "input": {
                "type": "text",
                "placeholder": "예시 입력"
            }
        }
    }

# EXAMPLE
def step_5():
    return {
        "messages": [bot("알레르기 정보를 알려주세요.")],
        "payload": {
            "question": "알레르기 정보",
            "input": {
                "type": "text",
                "placeholder": "ex) 꽃가루 알레르기"
            }
        }
    }


# ----------------------------------------
# 3. 시간 범위 선택 (time_range)
# ----------------------------------------

# TEMPLATE
def step_x_time_range():
    return {
        "messages": [
            bot("시간 범위를 선택해주세요."),
            bot("시작과 종료 시간을 골라주세요.")
        ],
        "payload": {
            "question": "시간 범위 선택",
            "input": {
                "type": "time_range"
            }
        }
    }

# EXAMPLE
def step_3():
    return {
        "messages": [
            bot("식물 관리가 가능한 시간을 입력해주세요."),
            bot("예시: 07:30 ~ 21:00")
        ],
        "payload": {
            "question": "식물 관리 가능 시간",
            "input": {
                "type": "time_range"
            }
        }
    }


# ----------------------------------------
# 4. 체크박스 필터 (filters)
# ----------------------------------------

# TEMPLATE
def step_x_filters():
    return {
        "messages": [bot("조건을 선택해주세요.")],
        "payload": {
            "type": "filters",
            "question": "속성 선택",
            "groups": [
                {
                    "key": "group_key",
                    "label": "그룹 이름",
                    "options": ["옵션1", "옵션2"]
                }
            ]
        }
    }

# EXAMPLE
def step_6():
    return {
        "messages": [bot("원하시는 속성을 체크해주세요(중복 가능)")],
        "payload": {
            "type": "filters",
            "question": "잎 색 / 열매 여부",
            "groups": [
                {
                    "key": "leafColors",
                    "label": "잎 색",
                    "options": ["녹색", "녹황색", "노란색"]
                },
                {
                    "key": "fruit",
                    "label": "열매",
                    "options": ["있음", "없음"]
                }
            ]
        }
    }


# ----------------------------------------
# 5. 이미지 업로드 (image)
# ----------------------------------------

# TEMPLATE
def step_x_image():
    return {
        "messages": [bot("이미지를 업로드해 주세요.")],
        "payload": {
            "question": "이미지 업로드",
            "input": {
                "type": "image"
            }
        }
    }

# EXAMPLE
def step_7():
    return {
        "messages": [bot("배치하려는 공간 사진을 업로드해 주세요.")],
        "payload": {
            "question": "공간 사진 업로드",
            "input": {
                "type": "image"
            }
        }
    }


# ----------------------------------------
# 6. 결과 출력 (photos + attributeSchema)
# ----------------------------------------

# TEMPLATE
def step_x_result():
    return {
        "messages": [bot("추천 결과입니다.")],
        "payload": {
            "photos": [
                {
                    "id": "item_id",
                    "label": "이름",
                    "imageUrl": "/assets/example.jpg",
                    "attributes": {
                        "속성1": "값",
                        "속성2": "값"
                    }
                }
            ],
            "attributeSchema": [
                {"key": "속성1", "label": "속성1"},
                {"key": "속성2", "label": "속성2"}
            ]
        }
    }

# EXAMPLE
def step_8_result():
    return {
        "messages": [bot("입력하신 조건에 맞는 식물입니다.")],
        "payload": {
            "photos": [
                {
                    "id": "plant1",
                    "label": "아레카야자",
                    "imageUrl": "/assets/areca_palm.jpg",
                    "attributes": {
                        "크기": "중형",
                        "관리난이도": "쉬움",
                        "반려동물": "안전"
                    }
                }
            ],
            "attributeSchema": [
                {"key": "크기", "label": "크기"},
                {"key": "관리난이도", "label": "관리 난이도"},
                {"key": "반려동물", "label": "반려동물 안전성"}
            ]
        }
    }


# ----------------------------------------
# 7. 메시지 출력만 (입력 없음)
# ----------------------------------------

# TEMPLATE
def step_x_info():
    return {
        "messages": [
            bot("안내 메시지입니다."),
            bot("다음 단계로 넘어갑니다.")
        ],
        "payload": {}
    }
