// 테스트용 업데이트 파일
export function testFunction(): string {
    return "version 1";
}

export class TestClass {
    private value: number = 1;
    
    getValue(): number {
        return this.value;
    }
}