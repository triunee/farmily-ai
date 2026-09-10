import chromium from '@sparticuz/chromium';
import puppeteer from 'puppeteer-core';
import { S3Client, GetObjectCommand, PutObjectCommand } from '@aws-sdk/client-s3';
import sharp from 'sharp';

const s3 = new S3Client({ region: process.env.AWS_REGION });

const TARGET_W = 1080;
const TARGET_H = 1350;

// 템플릿 종류별 렌더 설정
//  - 인스타(a/b/c): 1080×1350 고정 + 일반 스크린샷
//  - 스마트스토어: 가로 860 + fullPage(가변 높이) 스크린샷
const RENDER_CONFIG = {
  template_a: { width: TARGET_W, height: TARGET_H, fullPage: false },
  template_b: { width: TARGET_W, height: TARGET_H, fullPage: false },
  template_c: { width: TARGET_W, height: TARGET_H, fullPage: false },
  smartstore: { width: 860,      height: 1200,     fullPage: true  },
};

const PLACEHOLDER_MAP = {
  template_a: {
    1: { TITLE: 'mainTitle1' },
    2: { HEADING: 'mainTitle2', BODY: 'body1' },
    3: { HEADING: 'mainTitle3', BODY: 'body2', HIGHLIGHT_1: 'highlight1', HIGHLIGHT_2: 'highlight2' },
    4: { TITLE: 'closing' },
  },
  template_b: {
    1: { CATEGORY: 'category', TITLE: 'mainTitle1', SUBTITLE: 'subTitle' },
    2: { KEYWORD: 'highlight1', TITLE: 'mainTitle2', BODY: 'body1' },
    3: { KEYWORD: 'highlight2', TITLE: 'mainTitle3', BODY: 'body2' },
    4: { QUESTION: 'closing', HANDLE: 'handle', CTA: 'cta' },
  },
  template_c: {
    1: { CATEGORY: 'category', TITLE: 'mainTitle1', SUBTITLE: 'subTitle' },
    2: { TITLE: 'mainTitle2', BODY: 'body1' },
    3: { TITLE: 'mainTitle3', BODY: 'body2' },
    4: { QUESTION: 'closing', HANDLE: 'handle', CTA: 'cta' },
  },
  // 스마트스토어 상세 카드(detail-split) — 토큰명 == textPool 필드명 (identity 매핑)
  smartstore: {
    1: { HERO_BADGE: 'HERO_BADGE', HERO_SUB: 'HERO_SUB', S1_TITLE: 'S1_TITLE', S1_DESC: 'S1_DESC' },
    2: { S2_TITLE: 'S2_TITLE', S2_DESC: 'S2_DESC' },
    3: { CHECK_TITLE: 'CHECK_TITLE', CHECK_1: 'CHECK_1', CHECK_2: 'CHECK_2', CHECK_3: 'CHECK_3' },
    4: {
      ITEMS_EN: 'ITEMS_EN', ITEMS_KO: 'ITEMS_KO',
      ITEM1_NUM: 'ITEM1_NUM', ITEM1_LABEL: 'ITEM1_LABEL', ITEM1_DESC: 'ITEM1_DESC',
      ITEM2_NUM: 'ITEM2_NUM', ITEM2_LABEL: 'ITEM2_LABEL', ITEM2_DESC: 'ITEM2_DESC',
      ITEM3_NUM: 'ITEM3_NUM', ITEM3_LABEL: 'ITEM3_LABEL', ITEM3_DESC: 'ITEM3_DESC',
      ITEM4_NUM: 'ITEM4_NUM', ITEM4_LABEL: 'ITEM4_LABEL', ITEM4_DESC: 'ITEM4_DESC',
    },
  },
};

// 이미지 토큰 → 사진 인덱스(photoS3Keys 원래 순서, 전 카드 통합 0~6). 스마트스토어 전용.
// 인스타(a/b/c)는 카드당 단일 {{IMAGE_URL}}이라 이 맵을 쓰지 않는다.
const IMAGE_MAP = {
  smartstore: {
    1: { HERO_IMAGE: 0 },
    2: { S2_IMAGE: 1 },
    3: { S3_IMAGE: 2 },
    4: { ITEM1_IMAGE: 3, ITEM2_IMAGE: 4, ITEM3_IMAGE: 5, ITEM4_IMAGE: 6 },
  },
};

async function loadTemplate(templateType, cardNo) {
  const res = await s3.send(new GetObjectCommand({
    Bucket: process.env.TEMPLATE_BUCKET,
    Key: `${templateType}/card${cardNo}.html`,
  }));
  return res.Body.transformToString('utf-8');
}

async function downloadAndResize(s3Key, templateType) {
  const res = await s3.send(new GetObjectCommand({
    Bucket: process.env.S3_BUCKET,
    Key: s3Key,
  }));
  const bytes = await res.Body.transformToByteArray();
  let pipeline = sharp(Buffer.from(bytes));
  if (templateType === 'smartstore') {
    // 슬롯 비율이 제각각(히어로 가로형·항목 정사각) → 비율 보존(축소만).
    // 실제 크롭은 템플릿의 background-size:cover가 슬롯별로 처리.
    pipeline = pipeline.resize(1280, 1280, { fit: 'inside', withoutEnlargement: true });
  } else {
    pipeline = pipeline.resize(TARGET_W, TARGET_H, { fit: 'cover', position: 'centre' });
  }
  const resized = await pipeline.jpeg({ quality: 90 }).toBuffer();
  return `data:image/jpeg;base64,${resized.toString('base64')}`;
}

async function buildHtml(templateType, cardNo, textPool, images) {
  const template = await loadTemplate(templateType, cardNo);

  // CDN 링크 제거 (VPC에서 TCP hang 방지) — 폰트는 /var/task/fonts/ 에서 로딩
  let html = template.replace(/<link[^>]*cdn\.jsdelivr\.net[^>]*\/?>/gi, '');

  // 텍스트 토큰 치환
  const textMap = (PLACEHOLDER_MAP[templateType] || PLACEHOLDER_MAP['template_b'])[cardNo] || {};
  for (const [placeholder, field] of Object.entries(textMap)) {
    html = html.replace(
      new RegExp(`\\{\\{${placeholder}\\}\\}`, 'g'),
      textPool[field] || ''
    );
  }

  // 이미지 토큰 치환
  const imgMap = (IMAGE_MAP[templateType] || {})[cardNo];
  if (imgMap) {
    // 스마트스토어: 토큰별 다중 이미지 (사진 부족 시 순환)
    for (const [token, idx] of Object.entries(imgMap)) {
      const url = images.length ? images[idx % images.length] : '';
      html = html.replace(new RegExp(`\\{\\{${token}\\}\\}`, 'g'), url);
    }
  } else {
    // 인스타: 카드당 단일 {{IMAGE_URL}} (카드 순서대로 사진 배정, 부족 시 순환)
    const url = images.length ? images[(cardNo - 1) % images.length] : '';
    html = html.replace(/\{\{IMAGE_URL\}\}/g, url);
  }
  return html;
}

async function renderCard(browser, templateType, cardNo, textPool, images, userId, jobId) {
  const cfg = RENDER_CONFIG[templateType] || RENDER_CONFIG['template_b'];
  const html = await buildHtml(templateType, cardNo, textPool, images);
  const page = await browser.newPage();
  await page.setViewport({ width: cfg.width, height: cfg.height, deviceScaleFactor: 2 });
  await page.setContent(html, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await new Promise(r => setTimeout(r, 300));

  const buffer = await page.screenshot(
    cfg.fullPage ? { type: 'png', fullPage: true } : { type: 'png' }
  );
  await page.close();

  const key = `generated/${userId}/${jobId}/card${cardNo}.png`;
  await s3.send(new PutObjectCommand({
    Bucket: process.env.S3_BUCKET,
    Key: key,
    Body: buffer,
    ContentType: 'image/png',
  }));

  return key;
}

export const handler = async (event) => {
  const { textPool, templateType = 'template_b', userId, jobId, photoS3Keys } = JSON.parse(event.body ?? JSON.stringify(event));

  if (!photoS3Keys || photoS3Keys.length === 0) {
    return { statusCode: 400, body: JSON.stringify({ error: 'photoS3Keys 필수' }) };
  }
  if (!textPool) {
    return { statusCode: 400, body: JSON.stringify({ error: 'textPool 필수' }) };
  }

  const uniqueKeys = [...new Set(photoS3Keys)];
  const resizedImages = await Promise.all(uniqueKeys.map(key => downloadAndResize(key, templateType)));
  const dataUrlMap = Object.fromEntries(uniqueKeys.map((key, i) => [key, resizedImages[i]]));
  // photoS3Keys 원래 순서로 정렬된 dataUrl 배열 (이미지 인덱스 매핑 기준)
  const images = photoS3Keys.map(key => dataUrlMap[key]);

  const browser = await puppeteer.launch({
    args: chromium.args,
    executablePath: await chromium.executablePath(),
    headless: chromium.headless,
  });

  try {
    const keys = await Promise.all(
      [1, 2, 3, 4].map(cardNo =>
        renderCard(browser, templateType, cardNo, textPool, images, userId, jobId)
      )
    );
    return { statusCode: 200, body: JSON.stringify({ keys }) };
  } finally {
    await browser.close();
  }
};
