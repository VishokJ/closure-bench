`timescale 1ns / 1ps

module tb;

  localparam int CLK_PERIOD = 8;
  localparam int P = 5;
  localparam int FRAME = 76 * P;   // clocks between frame_error pulses during a break

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = P;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  int cyc = 0;
  int fe_count = 0;
  int last_fe = 0;
  bit hold_low = 0;
  bit allow_valid = 0;
  int n_valid = 0;
  logic [7:0] got = 8'h00;

  always @(negedge clk) begin
    cyc++;
    if (frame_error) begin
      if (fe_count > 0 && (cyc - last_fe) != FRAME)
        $fatal(1, "frame_error spacing %0d, expected %0d", cyc - last_fe, FRAME);
      fe_count++;
      last_fe = cyc;
    end
    if (m_axis_tvalid) begin
      if (!allow_valid) $fatal(1, "m_axis_tvalid during break (tdata 0x%02h)", m_axis_tdata);
      got = m_axis_tdata;
      n_valid++;
    end
    if (overrun_error) $fatal(1, "unexpected overrun_error");
    if (hold_low && fe_count > 0 && !busy) $fatal(1, "busy dropped during break");
  end

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic do_reset();
    rst = 1'b0; wait_clks(2);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(2);
  endtask

  task automatic uart_send_byte(input byte unsigned b);
    int bit_clks = P * 8;
    rxd = 1'b0; wait_clks(bit_clks);
    for (int i = 0; i < 8; i++) begin
      rxd = b[i]; wait_clks(bit_clks);
    end
    rxd = 1'b1; wait_clks(bit_clks);
  endtask

  initial begin
    int guard;
    do_reset();
    wait_clks(20);

    // Line break: hold rxd low for three frame errors.
    rxd = 1'b0;
    hold_low = 1;
    guard = 0;
    while (fe_count < 3) begin
      wait_clks(1);
      guard++;
      if (guard > 5 * FRAME) $fatal(1, "only %0d frame errors during break", fe_count);
    end
    rxd = 1'b1;
    hold_low = 0;
    wait_clks(2 * FRAME);
    if (fe_count != 3) $fatal(1, "expected 3 frame errors, got %0d", fe_count);
    if (n_valid != 0) $fatal(1, "word delivered during break");

    // Receiver must recover and accept a normal byte afterwards.
    allow_valid = 1;
    uart_send_byte(8'hA5);
    wait_clks(4 * P * 8);
    if (n_valid != 1) $fatal(1, "expected 1 word after break, got %0d", n_valid);
    if (got !== 8'hA5) $fatal(1, "got 0x%02h, expected 0xA5", got);
    if (fe_count != 3) $fatal(1, "extra frame error after break");

    $display("PASS: %0d frame errors during break, recovery ok", fe_count);
    $finish;
  end

  initial begin
    #2ms;
    $fatal(1, "timeout");
  end

endmodule
