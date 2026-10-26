`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
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

  int bit_clks;
  bit found;
  logic [7:0] b;

  initial begin
    @(negedge clk);
    rst = 1'b1; wait_clks(3);
    rst = 1'b0; wait_clks(5);
    bit_clks = int'(prescale) * 8;
    b = 8'hA5;
    rxd = 1'b0; wait_clks(bit_clks);           // start bit
    for (int i = 0; i < 8; i++) begin
      rxd = b[i]; wait_clks(bit_clks);
    end
    rxd = 1'b0;                                 // bad (low) stop bit
    found = 0;
    for (int n = 0; n < 4 * bit_clks && !found; n++) begin
      @(negedge clk);
      if (frame_error) found = 1;
    end
    if (!found) $fatal(1, "frame_error never pulsed");
    if (m_axis_tvalid) $fatal(1, "word with bad stop bit was delivered");
    // Assert reset in the very cycle frame_error is high
    rst = 1'b1;
    @(negedge clk);
    if (frame_error !== 1'b0) $fatal(1, "frame_error not cleared by reset");
    if (busy !== 1'b0) $fatal(1, "busy not cleared by reset");
    if (m_axis_tvalid !== 1'b0) $fatal(1, "tvalid high after reset");
    @(negedge clk);
    if (frame_error !== 1'b0) $fatal(1, "frame_error high during reset");
    rxd = 1'b1;
    wait_clks(2);
    rst = 1'b0;
    wait_clks(10);
    if (frame_error !== 1'b0) $fatal(1, "frame_error high after reset");
    if (busy !== 1'b0) $fatal(1, "busy high after reset with idle line");
    $display("PASS");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
