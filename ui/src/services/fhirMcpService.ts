// Mock FHIR MCP Service for demonstration
export class FHIRMcpService {
  private static instance: FHIRMcpService;

  public static getService(): FHIRMcpService {
    if (!FHIRMcpService.instance) {
      FHIRMcpService.instance = new FHIRMcpService();
    }
    return FHIRMcpService.instance;
  }

  async searchPatients(searchTerm: string): Promise<any[]> {
    // Mock implementation
    return [
      {
        patient_id: '1',
        name: 'John Doe',
        birth_date: '1980-01-01',
        gender: 'male',
      },
      {
        patient_id: '2', 
        name: 'Jane Smith',
        birth_date: '1990-05-15',
        gender: 'female',
      },
    ];
  }

  async getComprehensivePatientData(patientId: string): Promise<any> {
    // Mock implementation
    return {
      patient_id: patientId,
      name: 'Mock Patient',
      birth_date: '1985-01-01',
      gender: 'unknown',
      conditions: [],
      medications: [],
      vital_signs: null,
    };
  }

  async testConnection(): Promise<any> {
    return {
      status: 'connected',
      message: 'Mock connection successful',
    };
  }
}