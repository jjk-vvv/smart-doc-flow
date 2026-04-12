declare module "luckysheet/dist/plugins/js/plugin.js";
declare module "luckysheet/dist/luckysheet.umd.js";

declare module "luckyexcel" {
  const LuckyExcel: {
    transformExcelToLucky: (
      file: File,
      callback: (exportJson: { sheets?: unknown[]; info?: Record<string, unknown> }) => void
    ) => void;
  };
  export default LuckyExcel;
}

declare module "pdfjs-dist" {
  const pdfjsDist: any;
  export = pdfjsDist;
}

declare module "*.svg" {
  import React = require("react");
  export const ReactComponent: React.FC<React.SVGProps<SVGSVGElement>>;
  const src: string;
  export default src;
}
