const fs = require('fs');
const path = require('path');

const svgPath = path.join(__dirname, '..', 'assets', 'knowledge-graph.svg');
const svgText = fs.readFileSync(svgPath, 'utf8');
const pathTags = svgText.match(/<path[^>]*d="[^"]+"[^>]*>/g) || [];

if (pathTags.length < 316) {
  throw new Error(`Expected at least 316 <path> tags in ${svgPath}, received ${pathTags.length}`);
}

console.log('W1 tag:', pathTags[315].replace(/d="[^"]+"/, 'd="..."'));
console.log('W2 tag:', pathTags[7].replace(/d="[^"]+"/, 'd="..."'));
