export interface ColumnConfig {
    id: string;
    title: string;
    visible: boolean;
    width: number;
    minWidth: number;
    resizable: boolean;
}
export const STATIC_COLUMNS: ColumnConfig[] = [
    {
        id: "title",
        title: "Title",
        visible: true,
        width: 260,
        minWidth: 220,
        resizable: true,
    },
    {
        id: "descriptor",
        title: "Descriptor",
        visible: true,
        width: 220,
        minWidth: 180,
        resizable: true,
    },
    {
        id: "provider",
        title: "Provider",
        visible: true,
        width: 120,
        minWidth: 100,
        resizable: true,
    },
    {
        id: "sources",
        title: "Sources",
        visible: true,
        width: 120,
        minWidth: 100,
        resizable: true,
    },
    {
        id: "actions",
        title: "Actions",
        visible: true,
        width: 120,
        minWidth: 100,
        resizable: false,
    },
];

export const COLUMNS_STORAGE_KEY = "mappings.columns.v3";
