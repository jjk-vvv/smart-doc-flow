const fs = require('fs');
const code = fs.readFileSync('components/knowledge-nexus/KnowledgeNexusNeo4j.tsx', 'utf-8');

function checkTags(code) {
  const regex = /<(\/?)([a-zA-Z0-9_.-]+)[^>]*?(\/?)>/g;
  let match;
  const stack = [];
  const errors = [];
  
  // ignore self-closing tags and standard void elements
  const voidElements = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);
  
  let line = 1;
  let lastIndex = 0;
  
  while ((match = regex.exec(code)) !== null) {
    const substr = code.substring(lastIndex, match.index);
    line += (substr.match(/\n/g) || []).length;
    lastIndex = match.index;
    
    const isClosing = match[1] === '/';
    const tagName = match[2];
    const isSelfClosing = match[3] === '/' || voidElements.has(tagName.toLowerCase());
    
    // ignore React fragments
    if (tagName === '' || tagName === undefined) continue;
    
    if (!isClosing && !isSelfClosing) {
      stack.push({ tag: tagName, line });
    } else if (isClosing) {
      if (stack.length === 0) {
        errors.push(`Line ${line}: Unexpected closing tag </${tagName}>`);
        continue;
      }
      
      const last = stack.pop();
      if (last.tag !== tagName) {
        errors.push(`Line ${line}: Mismatched tags. Expected </${last.tag}> (from line ${last.line}), found </${tagName}>`);
        // Try to recover by pushing the last one back if it looks like we just missed a closing tag
        stack.push(last);
      }
    }
  }
  
  if (stack.length > 0) {
    errors.push(`Unclosed tags: ${stack.map(s => `<${s.tag}> on line ${s.line}`).join(', ')}`);
  }
  
  return errors;
}

const errors = checkTags(code);
if (errors.length > 0) {
  console.log('Errors found:');
  console.log(errors.slice(0, 10).join('\n'));
} else {
  console.log('No JSX tag errors found!');
}
