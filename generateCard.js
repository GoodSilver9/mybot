const { classicCard } = require("songcard");
const path = require("path");

// song card 생성 함수
async function generateCard(data) {
  const cardImage = await classicCard({
    imageBg: data.imageBg,
    imageText: data.imageText,
    songArtist: data.songArtist,
    trackDuration: data.trackDuration,
    trackTotalDuration: data.trackTotalDuration,
    trackStream: data.trackStream,
    // fontPath: null,
  });
  return cardImage;
}

// 파이�에서 전달된 데이터 받기
const data = JSON.parse(process.argv[2]);
generateCard(data).then((cardImage) => {
  console.log(cardImage.toString("base64")); // Base64로 인코딩해 출력
});
