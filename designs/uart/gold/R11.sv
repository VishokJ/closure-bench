`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b0;
  logic [15:0] prescale = 16'd2;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  // start bit + 8 data bits, no stop bit
  task automatic send_bits(input byte unsigned b);
    int bit_clks = int'(prescale) * 8;
    rxd = 1'b0; wait_clks(bit_clks);
    for (int i = 0; i < 8; i++) begin
      rxd = b[i]; wait_clks(bit_clks);
    end
  endtask

  task automatic send_byte(input byte unsigned b);
    int bit_clks = int'(prescale) * 8;
    send_bits(b);
    rxd = 1'b1; wait_clks(bit_clks);
  endtask

  initial begin
    int n;
    wait_clks(2);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(10);

    // First word, sink not ready: it stays pending.
    send_byte(8'hA5);
    if (m_axis_tvalid !== 1'b1) $fatal(1, "first word not presented");
    if (m_axis_tdata !== 8'hA5) $fatal(1, "first word wrong: 0x%02h", m_axis_tdata);
    if (overrun_error !== 1'b0) $fatal(1, "unexpected overrun on first word");

    // Second word: wait for the overrun strobe during its stop bit.
    send_bits(8'h3C);
    rxd = 1'b1;
    n = 0;
    while (overrun_error !== 1'b1) begin
      @(negedge clk);
      n++;
      if (n > 64) $fatal(1, "overrun_error never pulsed");
    end
    if (m_axis_tvalid !== 1'b1) $fatal(1, "tvalid low at overrun");

    // Assert reset in the same cycle the strobe is high.
    rst = 1'b1;
    @(negedge clk);
    if (overrun_error !== 1'b0) $fatal(1, "overrun_error not cleared by reset");
    if (m_axis_tvalid !== 1'b0) $fatal(1, "tvalid not cleared by reset");
    if (busy !== 1'b0) $fatal(1, "busy not cleared by reset");
    @(negedge clk);
    if (overrun_error !== 1'b0) $fatal(1, "overrun_error high during reset");
    rst = 1'b0;

    repeat (40) begin
      @(negedge clk);
      if (overrun_error !== 1'b0) $fatal(1, "overrun_error high after reset");
      if (frame_error !== 1'b0) $fatal(1, "frame_error high after reset");
      if (m_axis_tvalid !== 1'b0) $fatal(1, "tvalid high after reset");
    end

    $display("PASS");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
