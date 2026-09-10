"""
AgentCore Memory 리소스 최초 1회 생성 스크립트.
ECS 배포 전 로컬 또는 Cloud9에서 한 번만 실행합니다.

실행:
  AWS_REGION=ap-northeast-2 python setup_memory.py
  (리전 미지원 시: AWS_REGION=us-west-2 python setup_memory.py)

출력된 memory_id를 ECS Task Definition 환경변수 AGENTCORE_MEMORY_ID에 설정합니다.
"""
import os
from bedrock_agentcore.memory import MemoryClient

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")

client = MemoryClient(region_name=REGION)

memory = client.create_memory_and_wait(
    name        = "farmily_user_memory",   # 하이픈 불가(패턴 [a-zA-Z][a-zA-Z0-9_]) → 언더스코어
    description = "Farmily 사용자별 농장 사실·콘텐츠 선호도 장기 메모리",
    strategies  = [
        {
            "semanticMemoryStrategy": {
                "name":        "facts",
                "description": "농장 위치, 작물 종류, 재배 방식, 인증 정보 등 사실",
                "namespaces":  ["/facts/{actorId}"],
            }
        },
        {
            "userPreferenceMemoryStrategy": {
                "name":        "preferences",
                "description": "선호 콘텐츠 각도, 문체 스타일, 반응 좋았던 키워드",
                "namespaces":  ["/preferences/{actorId}"],
            }
        },
        # summaries 전략 제거: session_id=job-{job_id}라 단일 job 요약은
        # 재사용 안 돼 무용(세션 미사용 결정). facts·preferences만으로 유저별 개인화 충분.
    ],
    event_expiry_days = 180,  # 6개월 보존 후 자동 만료
)

memory_id = memory.get("memoryId") or memory.get("memory_id") or str(memory)
print(f"\n✅ Memory 생성 완료")
print(f"   memory_id : {memory_id}")
print(f"   region    : {REGION}")
print(f"\nECS Task Definition 환경변수에 추가:")
print(f'   {{ "name": "AGENTCORE_MEMORY_ID", "value": "{memory_id}" }}')
