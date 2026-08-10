import type { FolderLink } from "@/lib/folderLinks";

const KIND_LABEL: Record<FolderLink["kind"], string> = {
  onedrive: "OneDrive",
  gdrive: "Drive",
  other: "Link",
};

export default function FolderLinks({
  links,
  className = "",
}: {
  links: FolderLink[];
  className?: string;
}) {
  if (!links.length) return null;
  return (
    <p className={`folder-links ${className}`.trim()} aria-label="関連フォルダ">
      {links.map((link) => (
        <a
          key={`${link.kind}:${link.url}`}
          href={link.url}
          target="_blank"
          rel="noreferrer"
          className={`folder-link folder-link-${link.kind}`}
          title={`${KIND_LABEL[link.kind]}: ${link.label}`}
        >
          <span className="folder-link-kind">{KIND_LABEL[link.kind]}</span>
          {link.label}
        </a>
      ))}
    </p>
  );
}
