# fonts

카드 렌더링 런타임에 필요한 폰트. 바이너리(약 16MB)는 저장소에 포함하지 않으니
아래에서 받아 이 디렉터리에 넣는다. 배포 패키지(zip / 레이어)에는 반드시 동봉해야 한다.

| 파일 | 용도 | 다운로드 |
|---|---|---|
| `PretendardVariable.ttf` | 본문 한글/영문 | https://github.com/orioncactus/pretendard/releases → `pretendard-*.zip` 안의 `public/variable/PretendardVariable.ttf` |
| `NotoColorEmoji.ttf` | 이모지 컬러 렌더 | https://github.com/googlefonts/noto-emoji/raw/main/fonts/NotoColorEmoji.ttf |

```sh
cd lambdas/card-renderer/fonts

# Pretendard
curl -sL -o pretendard.zip https://github.com/orioncactus/pretendard/releases/latest/download/pretendard.zip
unzip -j pretendard.zip 'public/variable/PretendardVariable.ttf' -d .
rm pretendard.zip

# Noto Color Emoji
curl -sL -o NotoColorEmoji.ttf https://github.com/googlefonts/noto-emoji/raw/main/fonts/NotoColorEmoji.ttf
```

`fonts.conf`가 이 디렉터리를 fontconfig 경로로 지정한다.
