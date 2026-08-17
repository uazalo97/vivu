import { Jimp } from "jimp";

async function main() {
  try {
    const image = await Jimp.read("src/VinFast-logo-2026-2.png");
    image.circle();
    image.resize({ w: 128, h: 128 });
    await image.write("public/favicon.png");
    console.log("Success");
  } catch (error) {
    console.error(error);
  }
}

main();
